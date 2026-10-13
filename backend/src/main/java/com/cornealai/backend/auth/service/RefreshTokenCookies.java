package com.cornealai.backend.auth.service;

import com.cornealai.backend.security.SecurityProperties;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Optional;

/**
 * Builds the HttpOnly refresh-token cookie. It is scoped to the auth endpoints
 * and SameSite=Strict, so it is never sent with ordinary API calls.
 */
@Component
public class RefreshTokenCookies {

    private final SecurityProperties.RefreshToken properties;

    public RefreshTokenCookies(SecurityProperties securityProperties) {
        this.properties = securityProperties.refreshToken();
    }

    public ResponseCookie create(RefreshTokenService.IssuedRefreshToken token) {
        ResponseCookie.ResponseCookieBuilder builder = base(token.value());

        // Without "remember me" the cookie lasts for the browser session only.
        if (token.rememberMe()) {
            builder.maxAge(Duration.between(Instant.now(), token.expiresAt()));
        }

        return builder.build();
    }

    public ResponseCookie clear() {
        return base("").maxAge(0).build();
    }

    public Optional<String> read(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) {
            return Optional.empty();
        }

        return Arrays.stream(cookies)
                .filter(cookie -> properties.cookieName().equals(cookie.getName()))
                .map(Cookie::getValue)
                .filter(value -> !value.isBlank())
                .findFirst();
    }

    private ResponseCookie.ResponseCookieBuilder base(String value) {
        return ResponseCookie.from(properties.cookieName(), value)
                .httpOnly(true)
                .secure(properties.cookieSecure())
                .sameSite("Strict")
                .path(properties.cookiePath());
    }
}
