package com.cornealai.backend.common.error;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;
import java.util.Map;

/**
 * Error body returned by the API. Messages are safe for display and never
 * contain stack traces or internal details. {@code code} is a stable,
 * machine-readable reason (e.g. INVALID_IMAGE_DOMAIN) where one exists.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiError(
        Instant timestamp,
        int status,
        String error,
        String code,
        String message,
        String path,
        Map<String, String> fieldErrors
) {

    public static ApiError of(int status, String error, String message, String path) {
        return new ApiError(Instant.now(), status, error, null, message, path, null);
    }
}
