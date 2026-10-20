package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import com.cornealai.backend.analysis.repository.RecommendationAnalysisRunRepository;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RecommendationAnalysisIntegrationTests extends IntegrationTestSupport {

    private static final String MATCH_BODY = """
            {"request": {"requestId": "Q0001", "requestedGrade": "A+", "surgeryType": "PK"},
             "candidates": [{"recordId": "R0001", "grade": "A+", "ecd": 2800, "serologyClear": "Yes"},
                            {"recordId": "R0004", "grade": "A+", "serologyClear": "No"}]}""";
    private static final String FOLLOWUP_BODY = """
            {"graftId": "G0001", "procedure": "PK", "indication": "Fuchs/Endothelial", "donorAge": 60,
             "baselineEcd": 2700, "baselineCv": 36, "baselineHex": 56,
             "visit6m": {"ecd": 1700, "cv": 42, "hex": 50}, "visit12m": {"ecd": 1000, "cv": 46, "hex": 45},
             "rejectionBy12m": false}""";

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private RecommendationAnalysisRunRepository runs;

    private AppUser doctor;
    private JsonNode fixture;
    private final ObjectMapper snake = JsonMapper.builder()
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    @BeforeEach
    void setUp() throws Exception {
        doctor = createUser("dr.recommendation", RoleName.DOCTOR);
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_recommendation_responses.json")) {
            fixture = JsonMapper.builder().build().readTree(in);
        }
    }

    @Test
    void matchReturnsTheRankingAndRecordsTheRun() throws Exception {
        when(mlServiceClient.recommendMatch(any())).thenReturn(fixtureValue("match_completed", MatchResponse.class));

        call(doctor, "/match", MATCH_BODY)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.methodUsed").value("ml"))
                .andExpect(jsonPath("$.ranked[0].rank").value(1))
                .andExpect(jsonPath("$.ranked[0].recordId").value("R0001"))
                .andExpect(jsonPath("$.excluded[0].recordId").value("R0004"));

        RecommendationAnalysisRun run = runs.findBySubjectId("Q0001").getFirst();
        assertThat(run.getKind()).isEqualTo("match");
        assertThat(run.getStatus()).isEqualTo("completed");
        assertThat(run.getMethodUsed()).isEqualTo("ml");
        assertThat(run.getTopRecordId()).isEqualTo("R0001");
        assertThat(run.getRequestedBy()).isEqualTo(doctor.getId());
        assertThat(run.getResultJson()).contains("\"recordId\":\"R0001\"");
    }

    @Test
    void followupReturnsAlertAndNextVisitAndRecordsTheRun() throws Exception {
        when(mlServiceClient.recommendFollowup(any()))
                .thenReturn(fixtureValue("followup_completed", FollowupResponse.class));

        call(doctor, "/followup", FOLLOWUP_BODY)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.alert").value("red"))
                .andExpect(jsonPath("$.nextVisitMonths").value(3))
                .andExpect(jsonPath("$.predictedEcd[0].months").value(24))
                .andExpect(jsonPath("$.reasons.graftFailure[0].hazardRatio").isNumber());

        RecommendationAnalysisRun run = runs.findBySubjectId("G0001").getFirst();
        assertThat(run.getKind()).isEqualTo("followup");
        assertThat(run.getAlert()).isEqualTo("red");
        assertThat(run.getNextVisitMonths()).isEqualTo(3);
    }

    @Test
    void mlServiceRejectionIsPassedOnAndRecorded() throws Exception {
        when(mlServiceClient.recommendFollowup(any())).thenThrow(new AnalysisRejectedException(
                HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null, "The follow-up model is unavailable."));

        call(doctor, "/followup", FOLLOWUP_BODY)
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("MODEL_NOT_READY"));

        RecommendationAnalysisRun run = runs.findBySubjectId("G0001").getFirst();
        assertThat(run.getStatus()).isEqualTo("rejected");
        assertThat(run.getErrorCode()).isEqualTo("MODEL_NOT_READY");
    }

    @Test
    void emptyResultIsAnInferenceFailure() throws Exception {
        when(mlServiceClient.recommendFollowup(any())).thenReturn(new FollowupResponse(null, "G0001", null, null,
                null, null, null, null, null, null, null, null, null, null, null, null));

        call(doctor, "/followup", FOLLOWUP_BODY)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("MODEL_INFERENCE_FAILED"));
        assertThat(runs.findBySubjectId("G0001").getFirst().getStatus()).isEqualTo("rejected");
    }

    @Test
    void invalidInputIsRejectedBeforeCallingTheModel() throws Exception {
        call(doctor, "/followup", FOLLOWUP_BODY.replace("\"PK\"", "\"XYZ\"")).andExpect(status().isBadRequest());
        call(doctor, "/followup", FOLLOWUP_BODY.replace("\"visit12m\"", "\"other\"")).andExpect(status().isBadRequest());
        call(doctor, "/match", "{\"request\": {\"requestId\": \"Q1\", \"requestedGrade\": \"A\"}, \"candidates\": []}")
                .andExpect(status().isBadRequest());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void nonClinicalRoleCannotRunRecommendation() throws Exception {
        AppUser support = createUser("support.recommendation", RoleName.SUPPORT_STAFF);
        call(support, "/followup", FOLLOWUP_BODY).andExpect(status().isForbidden());
        call(support, "/match", MATCH_BODY).andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    private <T> T fixtureValue(String key, Class<T> type) {
        return snake.treeToValue(fixture.get(key), type);
    }

    private ResultActions call(AppUser user, String path, String body) throws Exception {
        return mockMvc.perform(post("/api/analysis/recommendation" + path)
                .header(HttpHeaders.AUTHORIZATION, bearer(user))
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }
}
