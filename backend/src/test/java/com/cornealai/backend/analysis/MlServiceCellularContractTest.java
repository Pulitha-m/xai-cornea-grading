package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.cellular.CellularBiomarkers;
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
 * Responses captured from the real ml-service POST /cellular/analyze (a validation specular microscopy image, the
 * ONNX models and the domain validator; overlay images replaced by a tiny JPEG) must map onto the backend DTOs.
 * Regenerate the fixture when the ml-service cellular schema changes.
 */
class MlServiceCellularContractTest {

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
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_cellular_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return strictMapper.readTree(in);
        }
    }

    private CellularAnalyzeResponse completed() throws Exception {
        return strictMapper.treeToValue(fixture().get("completed"), CellularAnalyzeResponse.class);
    }

    @Test
    void completedResponseMapsToDto() throws Exception {
        CellularAnalyzeResponse response = completed();

        assertEquals("completed", response.status());
        assertEquals("VALID_CORNEAL_IMAGE", response.imageValidation().domainStatus());
        assertEquals("roi_efficientnet_b0_stardist_onnx_v1", response.method());
        assertEquals(0.796, response.umPerPx(), 1e-9);
        assertTrue(response.validatedImageSize());
        CellularBiomarkers b = response.biomarkers();
        assertEquals(1421, b.cellCount());
        assertEquals(1e6 / (b.meanAreaUm2()), b.ecd(), 0.5);
        assertThat(b.coefficientOfVariation()).isBetween(0.0, 100.0);
        assertEquals(b.hexagonality(), b.sideDistributionPct().get("6"), 1e-9);
        assertThat(b.areaPercentilesUm2()).containsKeys("p5", "p50", "p95");
        assertThat(response.uncertainty().ecdCi95()).hasSize(2);
        assertThat(response.uncertainty().ecdCi95().get(0)).isLessThanOrEqualTo(b.ecd());
        assertThat(response.uncertainty().ecdCi95().get(1)).isGreaterThanOrEqualTo(b.ecd());
        assertEquals(b.cellCount(), response.reliability().green() + response.reliability().yellow()
                + response.reliability().red());
        assertTrue(response.reliable());
        assertThat(response.images().overlayJpeg()).startsWith("/9j/");
        assertTrue(response.message().contains("not a clinical measurement"));
    }

    @Test
    void auditCopyHasNoImages() throws Exception {
        CellularAnalyzeResponse response = completed();
        CellularAnalyzeResponse stripped = response.withoutImages();
        assertNull(stripped.images());
        assertEquals(response.biomarkers(), stripped.biomarkers());
        assertEquals(response.uncertainty(), stripped.uncertainty());
    }

    @Test
    void clientRaisesDomainRejectionWithItsCode() throws Exception {
        String body = strictMapper.writeValueAsString(fixture().get("rejected_domain"));
        MlServiceClient client = clientFor(422, body, new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeCellular("case-1", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("INVALID_IMAGE_DOMAIN", e.getCode());
                    assertEquals("image", e.getField());
                });
    }

    @Test
    void clientSendsMultipartToTheCellularEndpoint() throws Exception {
        AtomicReference<String> contentType = new AtomicReference<>();
        String body = strictMapper.writeValueAsString(fixture().get("completed"));
        MlServiceClient client = clientFor(200, body, contentType);

        CellularAnalyzeResponse response = client.analyzeCellular("case-1", new byte[]{1, 2, 3}, "image.jpg");

        assertThat(contentType.get()).startsWith("multipart/form-data");
        assertEquals(1421, response.biomarkers().cellCount());
    }

    @Test
    void clientDoesNotExposeUnstructuredErrors() throws Exception {
        MlServiceClient client = clientFor(500, "<html>Traceback (most recent call last)...</html>", new AtomicReference<>());

        assertThatThrownBy(() -> client.analyzeCellular("case-1", new byte[]{1}, "image.jpg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MODEL_INFERENCE_FAILED", e.getCode());
                    assertThat(e.getMessage()).doesNotContain("Traceback");
                });
    }

    private MlServiceClient clientFor(int status, String body, AtomicReference<String> contentType) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/cellular/analyze", exchange -> {
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
