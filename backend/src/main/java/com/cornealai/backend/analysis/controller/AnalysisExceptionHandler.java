package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.common.error.ApiError;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.time.Instant;
import java.util.Map;

/** Maps analysis rejections to the standard {@link ApiError} body, with a machine-readable code. */
@RestControllerAdvice
public class AnalysisExceptionHandler {

    @ExceptionHandler(AnalysisRejectedException.class)
    public ResponseEntity<ApiError> handleRejected(AnalysisRejectedException e, HttpServletRequest request) {
        ApiError body = new ApiError(
                Instant.now(),
                e.getStatus().value(),
                e.getStatus().getReasonPhrase(),
                e.getCode(),
                e.getMessage(),
                request.getRequestURI(),
                e.getFieldErrors().isEmpty() ? null : e.getFieldErrors()
        );
        return ResponseEntity.status(e.getStatus()).body(body);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiError> handleTooLarge(HttpServletRequest request) {
        return build(HttpStatus.CONTENT_TOO_LARGE, "IMAGE_TOO_LARGE", "file",
                "The image is larger than the upload limit.", request);
    }

    private static ResponseEntity<ApiError> build(
            HttpStatus status, String code, String field, String message, HttpServletRequest request
    ) {
        ApiError body = new ApiError(
                Instant.now(),
                status.value(),
                status.getReasonPhrase(),
                code,
                message,
                request.getRequestURI(),
                field == null ? null : Map.of(field, message)
        );
        return ResponseEntity.status(status).body(body);
    }
}
