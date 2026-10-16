package com.cornealai.backend.analysis;

import org.springframework.http.HttpStatus;

/**
 * An image upload or analysis request was refused. {@code code} is the stable
 * reason shown to clients (e.g. INVALID_IMAGE_DOMAIN); the message is safe to display.
 */
public class AnalysisRejectedException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final String field;

    public AnalysisRejectedException(HttpStatus status, String code, String field, String message) {
        super(message);
        this.status = status;
        this.code = code;
        this.field = field;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public String getField() {
        return field;
    }
}
