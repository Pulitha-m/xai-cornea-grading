package com.cornealai.backend.user.dto;

import com.cornealai.backend.user.entity.RoleName;
import jakarta.validation.constraints.NotNull;

public record UpdateRoleRequest(
        @NotNull
        RoleName role
) {
}
