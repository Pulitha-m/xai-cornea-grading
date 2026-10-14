package com.cornealai.backend.user.repository;

import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface AppUserRepository extends JpaRepository<AppUser, Long> {

    /** Identifiers are stored lower-cased, so callers must normalise before querying. */
    @Query("select u from AppUser u where u.username = :identifier or u.email = :identifier")
    Optional<AppUser> findByUsernameOrEmail(String identifier);

    boolean existsByUsername(String username);

    boolean existsByEmail(String email);

    boolean existsByRole_Name(RoleName roleName);

    long countByRole_NameAndEnabledTrue(RoleName roleName);

    List<AppUser> findAllByOrderByFullNameAsc();
}
