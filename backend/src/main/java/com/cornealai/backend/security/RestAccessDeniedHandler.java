package com.cornealai.backend.security;

import com.cornealai.backend.common.error.ApiErrorWriter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.stereotype.Component;

import java.io.IOException;

/** Returns 403 JSON when an authenticated user lacks permission (or a CSRF check fails). */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final ApiErrorWriter errorWriter;

    public RestAccessDeniedHandler(ApiErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException accessDeniedException
    ) throws IOException {
        String message = accessDeniedException instanceof CsrfException
                ? "Invalid or missing CSRF token."
                : "You do not have permission to perform this action.";

        errorWriter.write(request, response, HttpStatus.FORBIDDEN, message);
    }
}
