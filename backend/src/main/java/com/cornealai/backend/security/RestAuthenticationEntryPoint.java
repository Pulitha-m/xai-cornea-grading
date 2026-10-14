package com.cornealai.backend.security;

import com.cornealai.backend.common.error.ApiErrorWriter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

import java.io.IOException;

/** Returns 401 JSON for unauthenticated access to protected endpoints. */
@Component
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final ApiErrorWriter errorWriter;

    public RestAuthenticationEntryPoint(ApiErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException
    ) throws IOException {
        boolean invalidToken = request.getAttribute(JwtAuthenticationFilter.INVALID_TOKEN_ATTRIBUTE) != null;

        if (invalidToken) {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer error=\"invalid_token\"");
            errorWriter.write(request, response, HttpStatus.UNAUTHORIZED, "Your session has expired. Please sign in again.");
        } else {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
            errorWriter.write(request, response, HttpStatus.UNAUTHORIZED, "Authentication is required.");
        }
    }
}
