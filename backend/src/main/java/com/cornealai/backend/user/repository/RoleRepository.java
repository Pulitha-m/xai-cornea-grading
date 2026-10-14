package com.cornealai.backend.user.repository;

import com.cornealai.backend.user.entity.Role;
import com.cornealai.backend.user.entity.RoleName;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface RoleRepository extends JpaRepository<Role, Integer> {

    Optional<Role> findByName(RoleName name);
}
