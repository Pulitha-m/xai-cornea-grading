package com.cornealai.backend.analysis;

import org.springframework.http.HttpStatus;

import java.util.Map;

/**
 * An image upload or analysis request was refused. {@code code} is the stable
 * reason shown to clients (e.g. INVALID_IMAGE_DOMAIN); messages are safe to display.
 * {@code fieldErrors} lists every invalid field when there are several.
 */
public class AnalysisRejectedException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final String field;
    private final Map<String, String> fieldErrors;

    public AnalysisRejectedException(HttpStatus status, String code, String field, String message) {
        this(status, code, field, message, field == null ? Map.of() : Map.of(field, message));
    }

    public AnalysisRejectedException(HttpStatus status, String code, String field, String message,
                                     Map<String, String> fieldErrors) {
        super(message);
        this.status = status;
        this.code = code;
        this.field = field;
        this.fieldErrors = Map.copyOf(fieldErrors);
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

    public Map<String, String> getFieldErrors() {
        return fieldErrors;
    }
}
