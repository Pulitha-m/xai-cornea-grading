package com.cornealai.backend.auth.service;

import com.cornealai.backend.auth.dto.AuthResponse;
import com.cornealai.backend.auth.dto.LoginRequest;
import com.cornealai.backend.auth.dto.UserProfileResponse;
import com.cornealai.backend.common.error.ApiException;
import com.cornealai.backend.security.AppUserDetails;
import com.cornealai.backend.security.AppUserDetailsService;
import com.cornealai.backend.security.JwtService;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.repository.AppUserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;

@Service
public class AuthService {

    /** Same message for unknown users, wrong passwords, locked and disabled accounts. */
    private static final String INVALID_CREDENTIALS = "Invalid username/email or password.";

    private final AuthenticationManager authenticationManager;
    private final LoginAttemptService loginAttemptService;
    private final RefreshTokenService refreshTokenService;
    private final JwtService jwtService;
    private final AppUserRepository userRepository;

    public AuthService(
            AuthenticationManager authenticationManager,
            LoginAttemptService loginAttemptService,
            RefreshTokenService refreshTokenService,
            JwtService jwtService,
            AppUserRepository userRepository
    ) {
        this.authenticationManager = authenticationManager;
        this.loginAttemptService = loginAttemptService;
        this.refreshTokenService = refreshTokenService;
        this.jwtService = jwtService;
        this.userRepository = userRepository;
    }

    // Not @Transactional: a failed attempt must be recorded even though login then fails.
    public AuthResult login(LoginRequest request) {
        String identifier = AppUserDetailsService.normalise(request.identifier());
        Authentication authentication;

        try {
            authentication = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(identifier, request.password()));
        } catch (BadCredentialsException e) {
            loginAttemptService.recordFailure(identifier);
            throw new ApiException(HttpStatus.UNAUTHORIZED, INVALID_CREDENTIALS);
        } catch (AuthenticationException e) {
            // Locked or disabled: deliberately indistinguishable from bad credentials.
            throw new ApiException(HttpStatus.UNAUTHORIZED, INVALID_CREDENTIALS);
        }

        AppUserDetails principal = (AppUserDetails) authentication.getPrincipal();
        AppUser user = loginAttemptService.recordSuccess(principal.getId());

        return issueTokens(user, refreshTokenService.issue(user, request.isRememberMe()));
    }

    public AuthResult refresh(String rawRefreshToken) {
        RefreshTokenService.Rotation rotation = refreshTokenService.rotate(rawRefreshToken);
        return issueTokens(rotation.user(), rotation.refreshToken());
    }

    public void logout(String rawRefreshToken) {
        refreshTokenService.revokeSession(rawRefreshToken);
    }

    @Transactional(readOnly = true)
    public UserProfileResponse currentUser(Long userId) {
        return userRepository.findById(userId)
                .map(UserProfileResponse::from)
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "Authentication is required."));
    }

    private AuthResult issueTokens(AppUser user, RefreshTokenService.IssuedRefreshToken refreshToken) {
        JwtService.AccessToken accessToken = jwtService.issueAccessToken(AppUserDetails.from(user));
        long expiresIn = Duration.between(Instant.now(), accessToken.expiresAt()).toSeconds();

        AuthResponse body = new AuthResponse(
                accessToken.value(),
                "Bearer",
                expiresIn,
                accessToken.expiresAt(),
                UserProfileResponse.from(user)
        );

        return new AuthResult(body, refreshToken);
    }

    public record AuthResult(AuthResponse body, RefreshTokenService.IssuedRefreshToken refreshToken) {
    }
}
