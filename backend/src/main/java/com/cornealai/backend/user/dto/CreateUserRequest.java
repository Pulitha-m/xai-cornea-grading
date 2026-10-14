package com.cornealai.backend.user.dto;

import com.cornealai.backend.user.entity.RoleName;
import jakarta.validation.constraints.*;

public record CreateUserRequest(
        @NotBlank
        @Size(min = 3, max = 50)
        @Pattern(regexp = "^[A-Za-z0-9._-]+$", message = "may contain only letters, digits, '.', '_' and '-'")
        String username,

        @NotBlank
        @Email
        @Size(max = 255)
        String email,

        @NotBlank
        @Size(max = 120)
        String fullName,

        @NotNull
        RoleName role,

        @NotBlank
        @Size(min = 12, max = 72, message = "must be between 12 and 72 characters")
        String password
) {
}
