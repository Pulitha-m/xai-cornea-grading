package com.cornealai.backend.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;
import java.util.List;

@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(
        Jwt jwt,
        RefreshToken refreshToken,
        Login login,
        Cors cors
) {

    public record Jwt(
            String secret,
            String issuer,
            String audience,
            Duration accessTokenTtl
    ) {
    }

    public record RefreshToken(
            String cookieName,
            String cookiePath,
            boolean cookieSecure,
            Duration rememberMeTtl,
            Duration sessionTtl,
            Duration reuseGracePeriod
    ) {
    }

    public record Login(
            int maxFailedAttempts,
            Duration lockoutDuration
    ) {
    }

    public record Cors(
            List<String> allowedOrigins
    ) {
    }
}
