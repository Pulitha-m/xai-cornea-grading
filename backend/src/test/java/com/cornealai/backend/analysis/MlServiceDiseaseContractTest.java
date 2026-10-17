package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.DiseaseFinding;
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
 * Responses captured from the real ml-service POST /disease/analyze (a test-set specular
 * microscopy image; Grad-CAM strings truncated) must map onto the backend DTOs. Regenerate
 * the fixture when the ml-service disease schema changes.
 */
class MlServiceDiseaseContractTest {

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
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_disease_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return strictMapper.readTree(in);
        }
    }

    @Test
    void completedResponseMapsToDto() throws Exception {
        DiseaseAnalyzeResponse response = strictMapper.treeToValue(fixture().get("completed"), DiseaseAnalyzeResponse.class);

        assertEquals("completed", response.status());
        assertTrue(response.imageValidation().qualityAssessed());
        assertTrue(response.inputCheck().passed());
        assertEquals("OK", response.imageQuality().rating());
        assertThat(response.diseases()).extracting(DiseaseFinding::code)
                .containsExactly("FECD", "Guttata", "Folds", "PolyPleo", "LowCD");
        for (DiseaseFinding finding : response.diseases()) {
            assertEquals(finding.detected(), finding.probability() >= finding.threshold());
            assertEquals(finding.detected(), finding.gradcamPng() != null);
        }
        assertThat(response.overallSeverity()).isIn("None", "Mild", "Mod/Sev");
        assertThat(response.severityProbabilities()).containsKeys("FECDgroup", "Folds", "Guttata");
        assertTrue(response.message().contains("not a medical diagnosis"));
    }

    @Test
    void auditCopyHasNoGradcamImages() throws Exception {
        DiseaseAnalyzeResponse response = strictMapper.treeToValue(fixture().get("completed"), DiseaseAnalyzeResponse.class);
        assertThat(response.withoutGradcam().diseases()).allMatch(d -> d.gradcamPng() == null);
        assertThat(response.withoutGradcam().detected()).isEqualTo(response.detected());
    }

    @Test
    void clientReturnsFailedInputChecksWithEveryErrorAndWarning() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("input_check_failed"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        DiseaseAnalyzeResponse response = client.analyzeDisease("case-1", "{}", false, new byte[]{1}, "image.jpg");

        assertEquals(DiseaseAnalyzeResponse.INPUT_CHECK_FAILED, response.status());
        assertFalse(response.inputCheck().passed());
        assertThat(response.inputCheck().errors()).extracting(e -> e.code()).contains("VALUE_NOT_POSSIBLE");
        assertThat(response.inputCheck().warnings()).extracting(w -> w.code()).contains("VALUE_MISSING");
        assertNotNull(response.imageQuality());
        assertNull(response.diseases());
    }

    @Test
    void clientRaisesOtherRejectionsWithTheirFields() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("rejected_measurements"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeDisease("case-1", "{}", false, new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("FEATURE_SCHEMA_MISMATCH", e.getCode());
                    assertThat(e.getFieldErrors()).containsKeys("SD", "CV", "HEX_percent", "Donor_Age");
                });
    }

    @Test
    void clientSendsMultipartToTheDiseaseEndpoint() throws Exception {
        AtomicReference<String> contentType = new AtomicReference<>();
        String body = strictMapper.writeValueAsString(fixture().get("completed"));
        MlServiceClient client = clientFor(200, body, contentType);

        DiseaseAnalyzeResponse response = client.analyzeDisease("case-1", "{}", true, new byte[]{1, 2, 3}, "image.jpg");

        assertThat(contentType.get()).startsWith("multipart/form-data");
        assertEquals("completed", response.status());
    }

    @Test
    void clientDoesNotExposeUnstructuredErrors() throws Exception {
        MlServiceClient client = clientFor(500, "<html>Traceback (most recent call last)...</html>", new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeDisease("case-1", "{}", false, new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MODEL_INFERENCE_FAILED", e.getCode());
                    assertThat(e.getMessage()).doesNotContain("Traceback");
                });
    }

    private MlServiceClient clientFor(int status, String body, AtomicReference<String> contentType) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/disease/analyze", exchange -> {
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
