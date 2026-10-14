package com.cornealai.backend.auth.repository;

import com.cornealai.backend.auth.entity.RefreshToken;
import com.cornealai.backend.auth.entity.RevocationReason;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.Instant;
import java.util.Optional;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, Long> {

    @Query("select t from RefreshToken t join fetch t.user u join fetch u.role where t.tokenHash = :tokenHash")
    Optional<RefreshToken> findByTokenHash(String tokenHash);

    /**
     * Atomically marks a token as rotated. Returns 0 if another request already
     * revoked it, which guards against two concurrent refreshes both succeeding.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update RefreshToken t
               set t.revokedAt = :now, t.revokedReason = com.cornealai.backend.auth.entity.RevocationReason.ROTATED
             where t.id = :id and t.revokedAt is null
            """)
    int markRotated(Long id, Instant now);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update RefreshToken t
               set t.revokedAt = :now, t.revokedReason = :reason
             where t.familyId = :familyId and t.revokedAt is null
            """)
    int revokeFamily(String familyId, Instant now, RevocationReason reason);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update RefreshToken t
               set t.revokedAt = :now, t.revokedReason = :reason
             where t.user.id = :userId and t.revokedAt is null
            """)
    int revokeAllForUser(Long userId, Instant now, RevocationReason reason);

    @Modifying
    @Query("delete from RefreshToken t where t.expiresAt < :cutoff")
    int deleteExpiredBefore(Instant cutoff);
}
