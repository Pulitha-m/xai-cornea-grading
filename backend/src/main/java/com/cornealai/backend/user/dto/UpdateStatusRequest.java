package com.cornealai.backend.user.dto;

import jakarta.validation.constraints.NotNull;

public record UpdateStatusRequest(
        @NotNull
        Boolean enabled
) {
}
