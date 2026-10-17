package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
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
 * Responses captured from the real ml-service POST /grading/analyze (a training-set specular
 * microscopy image, the real backbone and domain validator) must map onto the backend DTOs.
 * Regenerate the fixture when the ml-service grading schema changes.
 */
class MlServiceGradingContractTest {

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
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_grading_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return strictMapper.readTree(in);
        }
    }

    @Test
    void completedResponseMapsToDto() throws Exception {
        GradingAnalyzeResponse response = strictMapper.treeToValue(fixture().get("completed"), GradingAnalyzeResponse.class);

        assertEquals("completed", response.status());
        assertEquals("VALID_CORNEAL_IMAGE", response.imageValidation().domainStatus());
        assertEquals("hybrid_random_forest_24_resnet50", response.method());
        assertThat(response.grade()).isIn("A+", "A", "B");
        assertEquals(1.0, response.modelProbabilities().values().stream().mapToDouble(Double::doubleValue).sum(), 0.01);
        assertThat(response.featuresUsed()).hasSize(24).containsKey("ECD_CD_cells_per_mm2");
        assertEquals("ecd_threshold_tree", response.ecdReference().method());
        assertTrue(response.message().contains("Specialist confirmation required"));
    }

    @Test
    void missingEcdStillGradesButHasNoEcdReference() throws Exception {
        GradingAnalyzeResponse response = strictMapper.treeToValue(fixture().get("missing_ecd"), GradingAnalyzeResponse.class);
        assertNotNull(response.grade());
        assertEquals("review_required", response.ecdReference().status());
        assertTrue(response.reviewRequired());
        assertThat(response.featuresNotRecorded()).contains("ECD_CD_cells_per_mm2");
        assertNull(response.featuresUsed().get("ECD_CD_cells_per_mm2"));
    }

    @Test
    void clientRaisesFeatureRejectionsWithEveryField() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("rejected_features"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeGrading("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("INVALID_FEATURE_TYPE", e.getCode());
                    assertThat(e.getFieldErrors()).containsKeys("CV", "Descemet_Fold_Severity");
                });
    }

    @Test
    void clientSendsMultipartToTheGradingEndpoint() throws Exception {
        AtomicReference<String> contentType = new AtomicReference<>();
        String body = strictMapper.writeValueAsString(fixture().get("completed"));
        MlServiceClient client = clientFor(200, body, contentType);

        GradingAnalyzeResponse response = client.analyzeGrading("case-1", "{}", new byte[]{1, 2, 3}, "image.jpg");

        assertThat(contentType.get()).startsWith("multipart/form-data");
        assertEquals("completed", response.status());
    }

    @Test
    void clientDoesNotExposeUnstructuredErrors() throws Exception {
        MlServiceClient client = clientFor(500, "<html>Traceback (most recent call last)...</html>", new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeGrading("case-1", "{}", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MODEL_INFERENCE_FAILED", e.getCode());
                    assertThat(e.getMessage()).doesNotContain("Traceback");
                });
    }

    private MlServiceClient clientFor(int status, String body, AtomicReference<String> contentType) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/grading/analyze", exchange -> {
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
