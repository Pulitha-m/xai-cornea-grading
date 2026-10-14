package com.cornealai.backend.user.service;

import com.cornealai.backend.auth.entity.RevocationReason;
import com.cornealai.backend.auth.service.RefreshTokenService;
import com.cornealai.backend.common.error.ApiException;
import com.cornealai.backend.user.dto.CreateUserRequest;
import com.cornealai.backend.user.dto.UserResponse;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.Role;
import com.cornealai.backend.user.entity.RoleName;
import com.cornealai.backend.user.repository.AppUserRepository;
import com.cornealai.backend.user.repository.RoleRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/**
 * Administrator-controlled account management. Authorization is enforced on the
 * controller; this service adds guards that do not depend on the caller's role
 * (no self-demotion, no self-disable).
 */
@Service
public class UserService {

    private static final Logger log = LoggerFactory.getLogger(UserService.class);
    private static final int BCRYPT_MAX_BYTES = 72;

    private final AppUserRepository userRepository;
    private final RoleRepository roleRepository;
    private final PasswordEncoder passwordEncoder;
    private final RefreshTokenService refreshTokenService;

    public UserService(
            AppUserRepository userRepository,
            RoleRepository roleRepository,
            PasswordEncoder passwordEncoder,
            RefreshTokenService refreshTokenService
    ) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.passwordEncoder = passwordEncoder;
        this.refreshTokenService = refreshTokenService;
    }

    @Transactional(readOnly = true)
    public List<UserResponse> listUsers() {
        return userRepository.findAllByOrderByFullNameAsc().stream()
                .map(UserResponse::from)
                .toList();
    }

    @Transactional
    public UserResponse createUser(CreateUserRequest request) {
        String username = request.username().trim().toLowerCase(Locale.ROOT);
        String email = request.email().trim().toLowerCase(Locale.ROOT);

        if (userRepository.existsByUsername(username) || userRepository.existsByEmail(email)) {
            throw new ApiException(HttpStatus.CONFLICT, "A user with this username or email already exists.");
        }

        AppUser user = new AppUser();
        user.setUsername(username);
        user.setEmail(email);
        user.setFullName(request.fullName().trim());
        user.setRole(findRole(request.role()));
        user.setPasswordHash(encodePassword(request.password()));
        user.setEnabled(true);

        AppUser saved = userRepository.save(user);
        log.info("Created user id {} with role {}", saved.getId(), request.role());
        return UserResponse.from(saved);
    }

    @Transactional
    public UserResponse assignRole(Long userId, RoleName roleName, Long actingUserId) {
        if (Objects.equals(userId, actingUserId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "You cannot change your own role.");
        }

        AppUser user = findUser(userId);
        if (user.getRole().getName() != roleName) {
            user.setRole(findRole(roleName));
            refreshTokenService.revokeAllForUser(userId, RevocationReason.ACCOUNT_CHANGED);
            log.info("User id {} assigned role {} by user id {}", userId, roleName, actingUserId);
        }
        return UserResponse.from(user);
    }

    @Transactional
    public UserResponse setEnabled(Long userId, boolean enabled, Long actingUserId) {
        if (!enabled && Objects.equals(userId, actingUserId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "You cannot disable your own account.");
        }

        AppUser user = findUser(userId);
        user.setEnabled(enabled);
        if (!enabled) {
            refreshTokenService.revokeAllForUser(userId, RevocationReason.ACCOUNT_CHANGED);
        }
        log.info("User id {} {} by user id {}", userId, enabled ? "enabled" : "disabled", actingUserId);
        return UserResponse.from(user);
    }

    @Transactional
    public void resetPassword(Long userId, String newPassword, Long actingUserId) {
        AppUser user = findUser(userId);
        user.setPasswordHash(encodePassword(newPassword));
        user.setFailedLoginAttempts(0);
        user.setLockedUntil(null);
        refreshTokenService.revokeAllForUser(userId, RevocationReason.ACCOUNT_CHANGED);
        log.info("Password reset for user id {} by user id {}", userId, actingUserId);
    }

    private String encodePassword(String rawPassword) {
        // BCrypt ignores input beyond 72 bytes; reject rather than silently truncate.
        if (rawPassword.getBytes(StandardCharsets.UTF_8).length > BCRYPT_MAX_BYTES) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Password is too long.");
        }
        return passwordEncoder.encode(rawPassword);
    }

    private AppUser findUser(Long userId) {
        return userRepository.findById(userId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "User not found."));
    }

    private Role findRole(RoleName roleName) {
        return roleRepository.findByName(roleName)
                .orElseThrow(() -> new IllegalStateException("Role missing from database: " + roleName));
    }
}
