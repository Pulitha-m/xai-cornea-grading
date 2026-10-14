package com.cornealai.backend.auth.controller;

import com.cornealai.backend.auth.dto.AuthResponse;
import com.cornealai.backend.auth.dto.LoginRequest;
import com.cornealai.backend.auth.dto.UserProfileResponse;
import com.cornealai.backend.auth.service.AuthService;
import com.cornealai.backend.auth.service.RefreshTokenCookies;
import com.cornealai.backend.auth.service.RefreshTokenService;
import com.cornealai.backend.common.error.ApiException;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final RefreshTokenCookies refreshTokenCookies;

    public AuthController(AuthService authService, RefreshTokenCookies refreshTokenCookies) {
        this.authService = authService;
        this.refreshTokenCookies = refreshTokenCookies;
    }

    /**
     * Issues the XSRF-TOKEN cookie. The client echoes its value in the
     * X-XSRF-TOKEN header on login, refresh and logout.
     */
    @GetMapping("/csrf")
    public ResponseEntity<Void> csrf(CsrfToken csrfToken) {
        csrfToken.getToken(); // loading the deferred token writes the cookie
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest request) {
        AuthService.AuthResult result = authService.login(request);

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, refreshTokenCookies.create(result.refreshToken()).toString())
                .body(result.body());
    }

    @PostMapping("/refresh")
    public ResponseEntity<AuthResponse> refresh(HttpServletRequest request, HttpServletResponse response) {
        try {
            String refreshToken = refreshTokenCookies.read(request)
                    .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "Your session has expired. Please sign in again."));

            AuthService.AuthResult result = authService.refresh(refreshToken);

            return ResponseEntity.ok()
                    .header(HttpHeaders.SET_COOKIE, refreshTokenCookies.create(result.refreshToken()).toString())
                    .body(result.body());
        } catch (RefreshTokenService.StaleRefreshTokenException e) {
            throw e; // keep the newer cookie set by the concurrent refresh
        } catch (ApiException e) {
            response.addHeader(HttpHeaders.SET_COOKIE, refreshTokenCookies.clear().toString());
            throw e;
        }
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request) {
        refreshTokenCookies.read(request).ifPresent(authService::logout);

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, refreshTokenCookies.clear().toString())
                .build();
    }

    @GetMapping("/me")
    public UserProfileResponse me(@AuthenticationPrincipal AppUserDetails principal) {
        return authService.currentUser(principal.getId());
    }
}
