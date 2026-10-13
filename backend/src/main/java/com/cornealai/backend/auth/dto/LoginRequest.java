package com.cornealai.backend.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Login credentials. Any other fields sent by the client (e.g. a role) are ignored.
 */
public record LoginRequest(
        @NotBlank(message = "Username or email is required")
        @Size(max = 255)
        String identifier,

        @NotBlank(message = "Password is required")
        @Size(max = 128)
        String password,

        // Optional; a boxed type so an omitted field is not a deserialization error.
        Boolean rememberMe
) {

    public boolean isRememberMe() {
        return Boolean.TRUE.equals(rememberMe);
    }
}
