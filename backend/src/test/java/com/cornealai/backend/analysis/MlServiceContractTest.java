package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.GradingResult;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Responses captured from the real ml-service (real specular microscopy image, COCO photo)
 * must map onto the backend DTOs and error codes. Regenerate the fixture when the
 * ml-service schema changes (see ml-service/README.md).
 */
class MlServiceContractTest {

    private final ObjectMapper strictMapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    private JsonNode fixture() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_analyze_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return strictMapper.readTree(in);
        }
    }

    @Test
    void completedResponseMapsToDto() throws Exception {
        AnalyzeResponse response = strictMapper.treeToValue(fixture().get("completed"), AnalyzeResponse.class);
        GradingResult grading = response.grading();

        assertEquals("VALID_CORNEAL_IMAGE", response.imageValidation().domainStatus());
        assertFalse(response.imageValidation().qualityAssessed());
        assertEquals("completed", grading.status());
        assertEquals("hybrid_random_forest_24_resnet50", grading.method());
        assertEquals(1.0, grading.modelProbabilities().values().stream().mapToDouble(Double::doubleValue).sum(), 0.01);
        assertTrue(grading.message().contains("Specialist confirmation required"));
        assertEquals("ecd_threshold_tree", grading.ecdReference().method());
        assertEquals(2232.0, grading.ecdReference().ecdBand().lowerExclusive());
        assertEquals("not_implemented", response.cellular().status());
        assertEquals("not_implemented", response.disease().status());
        assertNull(response.disease().confidence());
    }

    @Test
    void missingEcdStillGradesButHasNoEcdReference() throws Exception {
        GradingResult grading = strictMapper.treeToValue(fixture().get("missing_ecd"), AnalyzeResponse.class).grading();
        assertNotNull(grading.grade());
        assertEquals("review_required", grading.ecdReference().status());
        assertTrue(grading.reviewRequired());
        assertTrue(grading.featuresNotRecorded().contains("ECD_CD_cells_per_mm2"));
    }

    @Test
    void clientMapsEveryFeatureErrorToItsField() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("rejected_features"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        assertThatThrownBy(() -> client.analyze("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MISSING_CLINICAL_FEATURES", e.getCode());
                    assertThat(e.getFieldErrors()).containsKeys("HEX_percent", "CV");
                });
    }

    @Test
    void clientReturnsCompletedResultAndSendsMultipart() throws Exception {
        AtomicReference<String> contentType = new AtomicReference<>();
        String body = strictMapper.writeValueAsString(fixture().get("completed"));
        MlServiceClient client = clientFor(200, body, contentType);

        AnalyzeResponse response = client.analyze("case-1", "{}", new byte[]{1, 2, 3}, "image.jpg");

        assertThat(contentType.get()).startsWith("multipart/form-data");
        assertEquals("A", response.grading().grade());
    }

    @Test
    void clientTranslatesStructuredRejection() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("rejected_domain"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        assertThatThrownBy(() -> client.analyze("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals(HttpStatus.UNPROCESSABLE_CONTENT, e.getStatus());
                    assertEquals("INVALID_IMAGE_DOMAIN", e.getCode());
                    assertEquals("image", e.getField());
                });
    }

    @Test
    void clientDoesNotExposeUnstructuredErrors() throws Exception {
        MlServiceClient client = clientFor(500, "<html>Traceback (most recent call last)...</html>", new AtomicReference<>());

        assertThatThrownBy(() -> client.analyze("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MODEL_INFERENCE_FAILED", e.getCode());
                    assertThat(e.getMessage()).doesNotContain("Traceback");
                });
    }

    @Test
    void unreachableServiceIsModelNotReady() {
        MlServiceClient client = new MlServiceClient("http://127.0.0.1:1", strictMapper);
        assertThatThrownBy(() -> client.analyze("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class,
                        e -> assertEquals("MODEL_NOT_READY", e.getCode()));
    }

    private MlServiceClient clientFor(int status, String body, AtomicReference<String> contentType) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/analyze", exchange -> {
            contentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
            exchange.getRequestBody().readAllBytes();
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", status == 500 ? "text/html" : "application/json");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
        return new MlServiceClient("http://127.0.0.1:" + server.getAddress().getPort(), strictMapper);
    }
}
