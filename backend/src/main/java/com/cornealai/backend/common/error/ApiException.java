package com.cornealai.backend.common.error;

import org.springframework.http.HttpStatus;

/** An error whose message is safe to return to the client as-is. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;

    public ApiException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
