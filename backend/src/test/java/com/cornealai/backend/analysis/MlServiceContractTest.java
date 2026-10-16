package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.GradingResult;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Checks that responses captured from ml-service deserialize into the backend DTOs
 * without losing fields. Regenerate the fixture when the ml-service schema changes.
 */
class MlServiceContractTest {

    private final ObjectMapper strictMapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    private JsonNode fixture() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_analyze_responses.json")) {
            assertNotNull(in, "Contract fixture missing");
            return strictMapper.readTree(in);
        }
    }

    @Test
    void completedGradingResponseMapsToDto() throws Exception {
        AnalyzeResponse response = strictMapper.treeToValue(fixture().get("completed"), AnalyzeResponse.class);
        GradingResult grading = response.grading();

        assertEquals("completed", grading.status());
        assertEquals("A", grading.grade());
        assertEquals("ecd_threshold_tree", grading.method());
        assertEquals(2400.0, grading.ecdUsed());
        assertEquals(2232.0, grading.ecdBand().lowerExclusive());
        assertEquals(2497.0, grading.ecdBand().upperInclusive());
        assertEquals(1.0, grading.bandDistribution().values().stream().mapToDouble(Double::doubleValue).sum(), 0.01);
        assertFalse(grading.reviewRequired());
        assertTrue(grading.message().contains("Specialist confirmation required"));
        assertEquals("not_implemented", response.cellular().status());
    }

    @Test
    void missingEcdResponseRequiresReview() throws Exception {
        GradingResult grading = strictMapper
                .treeToValue(fixture().get("review_required"), AnalyzeResponse.class)
                .grading();

        assertEquals("review_required", grading.status());
        assertNull(grading.grade());
        assertTrue(grading.reviewRequired());
    }
}
