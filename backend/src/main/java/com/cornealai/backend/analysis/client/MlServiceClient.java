package com.cornealai.backend.analysis.client;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Sends the actual image bytes and inputs to ml-service and returns its result.
 * ml-service rejections ({"status":"rejected","error":{code,field,message}}) are
 * re-raised with the same code and message; nothing is fabricated on failure.
 */
@Component
public class MlServiceClient {

    private static final Logger log = LoggerFactory.getLogger(MlServiceClient.class);

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public MlServiceClient(@Value("${ml.service.url}") String mlServiceUrl, ObjectMapper objectMapper) {
        this.restClient = RestClient.builder().baseUrl(mlServiceUrl).build();
        this.objectMapper = objectMapper;
    }

    public AnalyzeResponse analyze(String caseId, Double ecd, byte[] image, String filename) {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("caseId", caseId);
        if (ecd != null) {
            form.add("ecd", ecd.toString());
        }
        form.add("image", new NamedBytes(image, filename));

        try {
            return restClient.post()
                    .uri("/analyze")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(form)
                    .retrieve()
                    .body(AnalyzeResponse.class);
        } catch (RestClientResponseException e) {
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    private AnalysisRejectedException translate(RestClientResponseException e) {
        try {
            JsonNode error = objectMapper.readTree(e.getResponseBodyAsString()).path("error");
            if (error.hasNonNull("code") && error.hasNonNull("message")) {
                HttpStatus status = HttpStatus.resolve(e.getStatusCode().value());
                return new AnalysisRejectedException(
                        status == null ? HttpStatus.BAD_GATEWAY : status,
                        error.get("code").asString(),
                        error.hasNonNull("field") ? error.get("field").asString() : null,
                        error.get("message").asString());
            }
        } catch (RuntimeException ignored) {
            // Not a structured rejection; fall through.
        }
        log.warn("ml-service returned an unexpected {} response", e.getStatusCode().value());
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                "The analysis could not be completed. Try again later.");
    }

    /**
     * Multipart file part with a filename (required for FastAPI's UploadFile). The part's
     * content type is derived from the server-chosen extension (.jpg / .png).
     */
    private static final class NamedBytes extends ByteArrayResource {

        private final String filename;

        NamedBytes(byte[] data, String filename) {
            super(data);
            this.filename = filename;
        }

        @Override
        public String getFilename() {
            return filename;
        }
    }
}
