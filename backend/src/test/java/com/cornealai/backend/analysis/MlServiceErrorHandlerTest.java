package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.controller.MlServiceErrorHandler;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MlServiceErrorHandlerTest {

    @Test
    void passesMlServiceValidationErrorThrough() {
        String body = "{\"detail\":[{\"loc\":[\"body\",\"ecd\"],\"msg\":\"Input should be less than or equal to 6000\"}]}";
        HttpClientErrorException error = HttpClientErrorException.create(
                HttpStatus.UNPROCESSABLE_CONTENT, "Unprocessable Entity", new HttpHeaders(),
                body.getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);

        ResponseEntity<String> response = new MlServiceErrorHandler().handleMlServiceClientError(error);

        assertEquals(HttpStatus.UNPROCESSABLE_CONTENT, response.getStatusCode());
        assertEquals(body, response.getBody());
    }
}
