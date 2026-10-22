package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import com.cornealai.backend.analysis.repository.RecommendationAnalysisRunRepository;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;
import java.util.List;
import java.util.UUID;

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
                .andExpect(jsonPath("$.excluded[0].recordId").value("R0004"))
                .andExpect(jsonPath("$.warnings[0]").value(org.hamcrest.Matchers.containsString("14-day limit")));

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
                null, null, null, null, null, null, null, null, null, null, null, null, null, null));

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
        call(doctor, "/followup", FOLLOWUP_BODY.replace("Fuchs/Endothelial", "Keratoconus")).andExpect(status().isBadRequest());
        call(doctor, "/match", MATCH_BODY.replace("\"ecd\": 2800", "\"ecd\": 90000")).andExpect(status().isBadRequest());
        call(doctor, "/match", MATCH_BODY.replace("\"serologyClear\": \"Yes\"}", "\"serologyClear\": \"Yes\", \"daysInStorage\": 400}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void newRequestsGetTheNextFreeRequestIdAndReRunsKeepTheirs() throws Exception {
        when(mlServiceClient.recommendMatch(any())).thenReturn(fixtureValue("match_completed", MatchResponse.class));
        call(doctor, "/match", MATCH_BODY.replace("Q0001", "Q0950")).andExpect(status().isOk());
        String blank = MATCH_BODY.replace("\"requestId\": \"Q0001\", ", "");
        call(doctor, "/match", blank).andExpect(status().isOk());
        call(doctor, "/match", blank).andExpect(status().isOk());
        call(doctor, "/match", MATCH_BODY.replace("Q0001", "Q0950")).andExpect(status().isOk());   // re-run keeps its ID

        ArgumentCaptor<MatchRequest> sent = ArgumentCaptor.forClass(MatchRequest.class);
        verify(mlServiceClient, times(4)).recommendMatch(sent.capture());
        List<String> ids = sent.getAllValues().stream().map(r -> r.request().requestId()).toList();
        assertThat(ids.get(0)).isEqualTo("Q0950");
        assertThat(ids.get(1)).matches("Q[0-9]{4}");
        int first = Integer.parseInt(ids.get(1).substring(1));
        assertThat(first).isGreaterThan(950);
        assertThat(ids.get(2)).isEqualTo("Q%04d".formatted(first + 1));
        assertThat(ids.get(3)).isEqualTo("Q0950");
        assertThat(runs.findBySubjectId(ids.get(1))).hasSize(1);
    }

    @Test
    void idsMustBeStudyCodesNotRealTissueIds() throws Exception {
        call(doctor, "/match", MATCH_BODY.replace("Q0001", "REQ-1")).andExpect(status().isBadRequest());
        call(doctor, "/match", MATCH_BODY.replace("R0001", "12656R")).andExpect(status().isBadRequest());
        call(doctor, "/match", MATCH_BODY.replace("R0001", "r0001")).andExpect(status().isBadRequest());
        call(doctor, "/followup", FOLLOWUP_BODY.replace("G0001", "graft-1")).andExpect(status().isBadRequest());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void duplicateTissueIdsAndAllZeroWeightsAreRejectedAndRecorded() throws Exception {
        call(doctor, "/match", MATCH_BODY.replace("R0004", "R0001"))
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("DUPLICATE_TISSUE_ID"));
        call(doctor, "/match", MATCH_BODY.replace("\"candidates\":", "\"weights\": {\"gradeFit\": 0, \"endothelium\": 0, "
                + "\"serology\": 0, \"freshness\": 0, \"surgeryCompatibility\": 0}, \"candidates\":"))
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("INVALID_WEIGHTS"));
        verifyNoInteractions(mlServiceClient);
        assertThat(runs.findBySubjectId("Q0001")).extracting(RecommendationAnalysisRun::getErrorCode)
                .containsExactlyInAnyOrder("DUPLICATE_TISSUE_ID", "INVALID_WEIGHTS");
    }

    @Test
    void nonClinicalRoleCannotRunRecommendation() throws Exception {
        AppUser support = createUser("support.recommendation", RoleName.SUPPORT_STAFF);
        call(support, "/followup", FOLLOWUP_BODY).andExpect(status().isForbidden());
        call(support, "/match", MATCH_BODY).andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void previousRunsAreListedNewestFirstAndReopenWithInputsAndResult() throws Exception {
        when(mlServiceClient.recommendMatch(any())).thenReturn(fixtureValue("match_completed", MatchResponse.class));
        call(doctor, "/match", MATCH_BODY).andExpect(status().isOk());
        call(doctor, "/match", MATCH_BODY.replace("Q0001", "Q0002")).andExpect(status().isOk());
        when(mlServiceClient.recommendFollowup(any())).thenReturn(fixtureValue("followup_completed", FollowupResponse.class));
        call(doctor, "/followup", FOLLOWUP_BODY).andExpect(status().isOk());

        get(doctor, "/runs?kind=match")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(2))
                // both runs can share a timestamp, so their order is not checked here
                .andExpect(jsonPath("$.items[*].subjectId").value(org.hamcrest.Matchers.containsInAnyOrder("Q0001", "Q0002")))
                .andExpect(jsonPath("$.items[0].topRecordId").value("R0001"))
                .andExpect(jsonPath("$.items[0].methodUsed").value("ml"))
                .andExpect(jsonPath("$.items[0].requestedBy").isNotEmpty())
                .andExpect(jsonPath("$.nextBefore").doesNotExist());
        get(doctor, "/runs?kind=match&subject=q0001").andExpect(jsonPath("$.items.length()").value(1));
        get(doctor, "/runs?kind=match&limit=1")
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.nextBefore").isNotEmpty());
        get(doctor, "/runs?kind=followup")
                .andExpect(jsonPath("$.items[0].alert").value("red"))
                .andExpect(jsonPath("$.items[0].nextVisitMonths").value(3));
        get(doctor, "/runs?kind=other").andExpect(status().isUnprocessableContent());

        String id = runs.findBySubjectId("Q0001").getFirst().getId().toString();
        get(doctor, "/runs/" + id)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summary.subjectId").value("Q0001"))
                .andExpect(jsonPath("$.inputs.candidates[0].recordId").value("R0001"))
                .andExpect(jsonPath("$.result.ranked[0].recordId").value("R0001"));
        get(doctor, "/runs/" + UUID.randomUUID()).andExpect(status().isNotFound());
    }

    @Test
    void withoutSerologyAccessOnlyOwnRunsAreVisible() throws Exception {
        when(mlServiceClient.recommendMatch(any())).thenReturn(fixtureValue("match_completed", MatchResponse.class));
        call(doctor, "/match", MATCH_BODY).andExpect(status().isOk());
        AppUser nurse = createUser("nurse.recommendation", RoleName.NURSE);
        call(nurse, "/match", MATCH_BODY.replace("Q0001", "Q0009")).andExpect(status().isOk());

        get(nurse, "/runs?kind=match")
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].subjectId").value("Q0009"));
        String doctorsRun = runs.findBySubjectId("Q0001").getFirst().getId().toString();
        get(nurse, "/runs/" + doctorsRun).andExpect(status().isNotFound());
        get(doctor, "/runs?kind=match").andExpect(jsonPath("$.items.length()").value(2));

        AppUser support = createUser("support.runs", RoleName.SUPPORT_STAFF);
        get(support, "/runs?kind=match").andExpect(status().isForbidden());
    }

    private ResultActions get(AppUser user, String path) throws Exception {
        return mockMvc.perform(MockMvcRequestBuilders.get("/api/analysis/recommendation" + path)
                .header(HttpHeaders.AUTHORIZATION, bearer(user)));
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
