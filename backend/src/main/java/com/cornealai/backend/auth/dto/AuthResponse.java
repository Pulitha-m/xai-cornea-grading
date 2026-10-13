package com.cornealai.backend.auth.dto;

import java.time.Instant;

public record AuthResponse(
        String accessToken,
        String tokenType,
        long expiresIn,
        Instant expiresAt,
        UserProfileResponse user
) {
}
