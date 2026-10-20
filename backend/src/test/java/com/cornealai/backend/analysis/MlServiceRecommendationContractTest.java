package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Responses captured from the real ml-service POST /recommendation/match and /followup (made-up candidates and
 * graft) must map onto the backend DTOs with nothing left over. Regenerate the fixture when the ml-service
 * recommendation schema changes.
 */
class MlServiceRecommendationContractTest {

    /** ml-service uses snake_case; strict, so a field added on either side fails the test. */
    private final ObjectMapper strictSnake = JsonMapper.builder()
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
    private final ObjectMapper plain = JsonMapper.builder().build();
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    private JsonNode fixture() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_recommendation_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return plain.readTree(in);
        }
    }

    @Test
    void matchResponseMapsToDto() throws Exception {
        MatchResponse r = strictSnake.treeToValue(fixture().get("match_completed"), MatchResponse.class);

        assertEquals("Q0001", r.requestId());
        assertEquals("ml", r.methodUsed());
        assertThat(r.ranked()).extracting(RankedCandidate::rank).containsExactly(1, 2, 3);
        assertThat(r.excluded()).containsExactly(new ExcludedCandidate("R0004", "positive serology"));
        RankedCandidate top = r.ranked().getFirst();
        assertNotNull(top.mlScore());
        assertThat(top.why()).isNotEmpty();
        assertThat(top.criterionScores()).containsKeys("grade_fit", "endothelium", "serology");
        assertThat(r.ranked().get(1).counterfactual()).contains("would be #1 if");
        assertTrue(r.disclaimer().contains("clinician"));
    }

    @Test
    void followupResponseMapsToDto() throws Exception {
        FollowupResponse r = strictSnake.treeToValue(fixture().get("followup_completed"), FollowupResponse.class);

        assertEquals("G0001", r.graftId());
        assertEquals("red", r.alert());
        assertEquals(3, r.nextVisitMonths());
        assertThat(r.predictedEcd()).extracting(PredictedEcd::months).containsExactly(24, 36, 60);
        r.predictedEcd().forEach(p -> assertThat(p.low()).isLessThanOrEqualTo(p.ecd()));
        assertThat(r.risk()).extracting(RiskEstimate::outcome).contains("graft_failure", "low_ecd");
        r.risk().forEach(x -> assertThat(x.probability()).isBetween(0.0, 1.0));
        assertThat(r.reasons().graftFailure()).isNotEmpty();
        assertThat(r.actions()).isNotEmpty();
        assertThat(r.counterfactuals()).allMatch(c -> c.contains("[descriptive]"));
        assertNotNull(r.dataSource());
        assertTrue(r.disclaimer().contains("clinician"));
        assertThat(r.alertThresholds()).containsKeys("red_failure_risk_12m", "amber_failure_risk_24m",
                "amber_low_ecd_risk_24m");
        assertThat(r.modelSummary()).containsKey("graft_failure_cv_c_index");
    }

    @Test
    void clientSendsSnakeCaseJsonAndReadsTheFollowupResponse() throws Exception {
        AtomicReference<String> sent = new AtomicReference<>();
        MlServiceClient client = clientFor("/recommendation/followup", 200,
                plain.writeValueAsString(fixture().get("followup_completed")), sent);

        FollowupResponse r = client.recommendFollowup(followupRequest());

        JsonNode body = plain.readTree(sent.get());
        assertEquals("G0001", body.get("graft_id").asString());
        assertEquals(1000.0, body.get("visit_12m").get("ecd").asDouble());
        assertTrue(body.get("visit_3m").isNull());
        assertFalse(body.get("rejection_by_12m").asBoolean());
        assertEquals("red", r.alert());
    }

    @Test
    void clientSendsMatchRequestInSnakeCaseWithoutNulls() throws Exception {
        AtomicReference<String> sent = new AtomicReference<>();
        MlServiceClient client = clientFor("/recommendation/match", 200,
                plain.writeValueAsString(fixture().get("match_completed")), sent);
        MatchRequest request = new MatchRequest(new MatchRequestInfo("Q0001", "A+", "PK", null),
                List.of(new MatchCandidate("R0001", "A+", 2800.0, null, null, 50.0, 3.0, 3.0, "Yes")), null, null, null);

        MatchResponse r = client.recommendMatch(request);

        JsonNode body = plain.readTree(sent.get());
        assertEquals("A+", body.get("request").get("requested_grade").asString());
        assertEquals(3.0, body.get("candidates").get(0).get("death_to_preservation_h").asDouble());
        assertFalse(body.get("candidates").get(0).has("cv"));            // nulls left out: ml-service defaults apply
        assertFalse(body.has("top_k"));
        assertEquals("ml", r.methodUsed());
    }

    @Test
    void clientRaisesValidationRejectionWithItsCode() throws Exception {
        MlServiceClient client = clientFor("/recommendation/followup", 422,
                plain.writeValueAsString(fixture().get("followup_rejected_invalid")), new AtomicReference<>());

        assertThatThrownBy(() -> client.recommendFollowup(followupRequest()))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("INVALID_REQUEST", e.getCode());
                    assertEquals("procedure", e.getField());
                });
    }

    @Test
    void clientRaisesModelNotReady() throws Exception {
        MlServiceClient client = clientFor("/recommendation/followup", 503,
                plain.writeValueAsString(fixture().get("followup_rejected_model_not_ready")), new AtomicReference<>());

        assertThatThrownBy(() -> client.recommendFollowup(followupRequest()))
                .isInstanceOfSatisfying(AnalysisRejectedException.class,
                        e -> assertEquals("MODEL_NOT_READY", e.getCode()));
    }

    @Test
    void clientDoesNotExposeUnstructuredErrors() throws Exception {
        MlServiceClient client = clientFor("/recommendation/match", 500,
                "<html>Traceback (most recent call last)...</html>", new AtomicReference<>());
        MatchRequest request = new MatchRequest(new MatchRequestInfo("Q1", "A", null, null),
                List.of(new MatchCandidate("R1", "A", null, null, null, null, null, null, null)), null, null, null);

        assertThatThrownBy(() -> client.recommendMatch(request))
                .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                    assertEquals("MODEL_INFERENCE_FAILED", e.getCode());
                    assertThat(e.getMessage()).doesNotContain("Traceback");
                });
    }

    static FollowupRequest followupRequest() {
        return new FollowupRequest("G0001", "PK", "Fuchs/Endothelial", 60.0, 2700.0, 36.0, 56.0, null,
                new FollowupVisit(1700.0, 42.0, 50.0), new FollowupVisit(1000.0, 46.0, 45.0), false);
    }

    private MlServiceClient clientFor(String path, int status, String body, AtomicReference<String> sent) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, exchange -> {
            sent.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", status == 500 ? "text/html" : "application/json");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
        return new MlServiceClient("http://127.0.0.1:" + server.getAddress().getPort(), plain);
    }
}
