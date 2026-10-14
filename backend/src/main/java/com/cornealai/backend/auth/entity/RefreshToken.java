package com.cornealai.backend.auth.entity;

import com.cornealai.backend.user.entity.AppUser;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/**
 * A refresh token. Only the SHA-256 hash of the token value is stored.
 * Tokens rotated from the same login share a {@code familyId}, so a whole
 * session can be revoked at once (logout or reuse detection).
 */
@Entity
@Table(name = "refresh_tokens")
@Getter
@Setter
@NoArgsConstructor
public class RefreshToken {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private AppUser user;

    @Column(name = "token_hash", nullable = false, unique = true, length = 64)
    private String tokenHash;

    @Column(name = "family_id", nullable = false, length = 36)
    private String familyId;

    @Column(name = "remember_me", nullable = false)
    private boolean rememberMe;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "revoked_reason", length = 32)
    private RevocationReason revokedReason;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
