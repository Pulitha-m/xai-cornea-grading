package com.cornealai.backend.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ResetPasswordRequest(
        @NotBlank
        @Size(min = 12, max = 72, message = "must be between 12 and 72 characters")
        String newPassword
) {
}
