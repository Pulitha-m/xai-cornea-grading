package com.cornealai.backend.auth.service;

import com.cornealai.backend.auth.entity.RefreshToken;
import com.cornealai.backend.auth.entity.RevocationReason;
import com.cornealai.backend.auth.repository.RefreshTokenRepository;
import com.cornealai.backend.common.error.ApiException;
import com.cornealai.backend.security.SecurityProperties;
import com.cornealai.backend.user.entity.AppUser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;

/**
 * Issues, rotates and revokes opaque refresh tokens.
 * <p>
 * Each refresh replaces the presented token with a new one. Presenting a token
 * that was already rotated is treated as theft and revokes the whole session,
 * except within a short grace period that tolerates concurrent refreshes from
 * multiple browser tabs. A session's absolute lifetime is fixed at login.
 */
@Service
public class RefreshTokenService {

    private static final Logger log = LoggerFactory.getLogger(RefreshTokenService.class);
    private static final int TOKEN_BYTES = 32;

    private final RefreshTokenRepository refreshTokenRepository;
    private final SecurityProperties.RefreshToken properties;
    private final SecureRandom secureRandom = new SecureRandom();

    public RefreshTokenService(
            RefreshTokenRepository refreshTokenRepository,
            SecurityProperties securityProperties
    ) {
        this.refreshTokenRepository = refreshTokenRepository;
        this.properties = securityProperties.refreshToken();
    }

    @Transactional
    public IssuedRefreshToken issue(AppUser user, boolean rememberMe) {
        Duration ttl = rememberMe ? properties.rememberMeTtl() : properties.sessionTtl();
        Instant expiresAt = Instant.now().plus(ttl);
        return create(user, UUID.randomUUID().toString(), rememberMe, expiresAt);
    }

    /**
     * @throws ApiException 401 if the token is unknown, expired, revoked or reused
     */
    @Transactional(noRollbackFor = ApiException.class)
    public Rotation rotate(String rawToken) {
        RefreshToken current = refreshTokenRepository.findByTokenHash(hash(rawToken))
                .orElseThrow(RefreshTokenService::invalidSession);

        Instant now = Instant.now();

        if (current.getRevokedAt() != null) {
            // Only a replayed *rotated* token indicates theft; logged-out or
            // administratively revoked tokens are simply rejected.
            if (current.getRevokedReason() == RevocationReason.ROTATED) {
                if (current.getRevokedAt().plus(properties.reuseGracePeriod()).isAfter(now)) {
                    // Another tab won the race; its new cookie is already in the browser.
                    throw new StaleRefreshTokenException();
                }

                refreshTokenRepository.revokeFamily(current.getFamilyId(), now, RevocationReason.REUSE_DETECTED);
                log.warn("Refresh token reuse detected; revoked session for user id {}", current.getUser().getId());
            }
            throw invalidSession();
        }

        AppUser user = current.getUser();

        if (!current.getExpiresAt().isAfter(now) || !user.isEnabled()) {
            throw invalidSession();
        }

        if (refreshTokenRepository.markRotated(current.getId(), now) == 0) {
            throw new StaleRefreshTokenException();
        }

        IssuedRefreshToken next = create(user, current.getFamilyId(), current.isRememberMe(), current.getExpiresAt());
        return new Rotation(user, next);
    }

    /** Revokes the session the given token belongs to. Unknown tokens are ignored. */
    @Transactional
    public void revokeSession(String rawToken) {
        refreshTokenRepository.findByTokenHash(hash(rawToken))
                .ifPresent(token -> refreshTokenRepository.revokeFamily(
                        token.getFamilyId(), Instant.now(), RevocationReason.LOGOUT));
    }

    @Transactional
    public void revokeAllForUser(Long userId, RevocationReason reason) {
        refreshTokenRepository.revokeAllForUser(userId, Instant.now(), reason);
    }

    @Scheduled(cron = "0 30 3 * * *")
    @Transactional
    public void purgeExpiredTokens() {
        int deleted = refreshTokenRepository.deleteExpiredBefore(Instant.now().minus(Duration.ofDays(1)));
        if (deleted > 0) {
            log.info("Purged {} expired refresh tokens", deleted);
        }
    }

    private IssuedRefreshToken create(AppUser user, String familyId, boolean rememberMe, Instant expiresAt) {
        byte[] bytes = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(bytes);
        String rawToken = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);

        RefreshToken token = new RefreshToken();
        token.setUser(user);
        token.setTokenHash(hash(rawToken));
        token.setFamilyId(familyId);
        token.setRememberMe(rememberMe);
        token.setExpiresAt(expiresAt);
        refreshTokenRepository.save(token);

        return new IssuedRefreshToken(rawToken, expiresAt, rememberMe);
    }

    private static String hash(String rawToken) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(rawToken.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    private static ApiException invalidSession() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "Your session has expired. Please sign in again.");
    }

    public record IssuedRefreshToken(String value, Instant expiresAt, boolean rememberMe) {
    }

    /**
     * The token was rotated moments ago by a concurrent request. The session is
     * still valid, so the caller must not clear the (already replaced) cookie.
     */
    public static class StaleRefreshTokenException extends ApiException {

        public StaleRefreshTokenException() {
            super(HttpStatus.UNAUTHORIZED, "Your session was refreshed in another tab. Please retry.");
        }
    }

    public record Rotation(AppUser user, IssuedRefreshToken refreshToken) {
    }
}
