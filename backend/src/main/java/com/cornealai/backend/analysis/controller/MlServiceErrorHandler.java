package com.cornealai.backend.analysis.controller;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.HttpClientErrorException;

@RestControllerAdvice
public class MlServiceErrorHandler {

    /**
     * ml-service rejected the request (e.g. ECD outside the valid range).
     * Pass its 4xx status and validation details through instead of a 500.
     */
    @ExceptionHandler(HttpClientErrorException.class)
    public ResponseEntity<String> handleMlServiceClientError(HttpClientErrorException e) {
        return ResponseEntity.status(e.getStatusCode())
                .contentType(MediaType.APPLICATION_JSON)
                .body(e.getResponseBodyAsString());
    }
}
