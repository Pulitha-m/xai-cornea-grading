package com.cornealai.backend.transplant;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.ExcludedCandidate;
import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchCandidate;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.dto.recommendation.RankedCandidate;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Matching from signed-off cases, allocation into grafts, and graft-based post-transplant follow-up. */
class TransplantIntegrationTests extends IntegrationTestSupport {

    @MockitoBean
    private MlServiceClient mlServiceClient;

    private AppUser doctor;
    private AppUser nurse;

    @BeforeEach
    void setUp() throws Exception {
        doctor = createUser("dr.transplant", RoleName.DOCTOR);
        nurse = createUser("nurse.transplant", RoleName.NURSE);

        // The ranker echoes the candidates it was given: positive serology excluded, the rest ranked in order.
        when(mlServiceClient.recommendMatch(any())).thenAnswer(invocation -> {
            MatchRequest request = invocation.getArgument(0);
            List<RankedCandidate> ranked = new ArrayList<>();
            List<ExcludedCandidate> excluded = new ArrayList<>();
            for (MatchCandidate c : request.candidates()) {
                if ("No".equals(c.serologyClear())) {
                    excluded.add(new ExcludedCandidate(c.recordId(), "positive serology"));
                } else {
                    ranked.add(new RankedCandidate(ranked.size() + 1, c.recordId(), c.grade(), 0.9, 0.8, 1, 0,
                            Map.of(), List.of("grade fits"), List.of(), null, null, List.of()));
                }
            }
            return new MatchResponse(null, request.request().requestId(), ranked, excluded, Map.of(), true, "ml",
                    "lightgbm_lambdarank", Map.of(), "Decision support.");
        });
        try (InputStream in = getClass().getResourceAsStream("/contracts/ml_service_recommendation_responses.json")) {
            JsonNode fixture = JsonMapper.builder().build().readTree(in);
            FollowupResponse followup = JsonMapper.builder()
                    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES).build()
                    .treeToValue(fixture.get("followup_completed"), FollowupResponse.class);
            when(mlServiceClient.recommendFollowup(any())).thenReturn(followup);
        }
    }

    @Test
    void matchingRanksTheSignedOffCorneasInStockByCaseNotByTissueId() throws Exception {
        String inStock = signedOffCase("12656R", LocalDate.now().minusDays(2), "Negative");
        String positive = signedOffCase("12657L", LocalDate.now().minusDays(1), "Positive");
        caseWithDetails("12658R", LocalDate.now());                        // not signed off
        signedOffCase("12659L", LocalDate.now().minusDays(20), "Negative"); // past the storage window

        call(nurse, post("/api/transplants/match").contentType(MediaType.APPLICATION_JSON).content(MATCH))
                .andExpect(status().isForbidden());
        call(doctor, post("/api/transplants/match").contentType(MediaType.APPLICATION_JSON).content(MATCH))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.considered").value(2))
                .andExpect(jsonPath("$.notInStock").value(1))
                .andExpect(jsonPath("$.match.ranked", hasSize(1)))
                .andExpect(jsonPath("$.match.ranked[0].recordId").value(inStock))
                .andExpect(jsonPath("$.match.excluded[0].recordId").value(positive))
                .andExpect(jsonPath("$.tissueIds['" + inStock + "']").value("12656R"))
                .andExpect(jsonPath("$.match.analysisId").isNotEmpty());

        ArgumentCaptor<MatchRequest> sent = ArgumentCaptor.forClass(MatchRequest.class);
        verify(mlServiceClient).recommendMatch(sent.capture());
        assertThat(sent.getValue().candidates()).extracting(MatchCandidate::recordId).containsExactlyInAnyOrder(inStock, positive);
        assertThat(sent.getValue().toString()).doesNotContain("1265");
        assertThat(sent.getValue().candidates()).filteredOn(c -> c.recordId().equals(inStock)).singleElement()
                .satisfies(c -> {
                    assertThat(c.grade()).isEqualTo("A");         // the confirmed grade
                    assertThat(c.ecd()).isEqualTo(2400.0);        // the sign-off value, not the case's 2500
                    assertThat(c.serologyClear()).isEqualTo("Yes");
                    assertThat(c.daysInStorage()).isEqualTo(2.0);
                });
    }

    @Test
    void allocationCreatesTheGraftAndTakesTheCorneaOutOfStock() throws Exception {
        String caseId = signedOffCase("12656R", LocalDate.now(), "Negative");
        String positive = signedOffCase("12657L", LocalDate.now(), "Positive");
        String unsigned = caseWithDetails("12658R", LocalDate.now());

        call(nurse, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON).content(allocate(caseId)))
                .andExpect(status().isForbidden());
        call(doctor, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON).content(allocate(caseId)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tissueId").value("12656R"))
                .andExpect(jsonPath("$.requestId").value("Q0001"))
                .andExpect(jsonPath("$.procedure").value("PK"))
                .andExpect(jsonPath("$.baselineEcd").value(2400.0))
                .andExpect(jsonPath("$.missing", hasItems("6-month visit", "12-month visit")));

        call(doctor, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON).content(allocate(caseId)))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("ALREADY_ALLOCATED"));
        call(doctor, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON).content(allocate(positive)))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("SEROLOGY_POSITIVE"));
        call(doctor, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON).content(allocate(unsigned)))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("NOT_SIGNED_OFF"));

        call(doctor, get("/api/cases/candidates"))
                .andExpect(jsonPath("$[*].recordId").value(org.hamcrest.Matchers.not(hasItems(caseId))));
        call(nurse, get("/api/transplants/grafts").param("caseId", caseId))
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].tissueId").value("12656R"));
        call(nurse, get("/api/transplants/grafts").param("caseId", unsigned)).andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void followUpIsBuiltFromTheGraftsVisitsAndTheConfirmedDonorValues() throws Exception {
        String caseId = signedOffCase("12656R", LocalDate.now(), "Negative");
        String graft = call(doctor, post("/api/transplants/grafts").contentType(MediaType.APPLICATION_JSON)
                .content(allocate(caseId))).andReturn().getResponse().getContentAsString()
                .replaceAll("^\\{\"id\":\"([0-9a-f-]{36})\".*", "$1");

        call(nurse, post("/api/transplants/grafts/" + graft + "/followups"))
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("FOLLOWUP_INPUT_MISSING"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("6-month visit")));

        call(nurse, put("/api/transplants/grafts/" + graft + "/visits/9").contentType(MediaType.APPLICATION_JSON)
                .content("{\"ecd\":1700,\"cv\":42,\"hex\":50}")).andExpect(status().isBadRequest());
        call(nurse, put("/api/transplants/grafts/" + graft + "/visits/6").contentType(MediaType.APPLICATION_JSON)
                .content("{\"ecd\":0,\"cv\":42,\"hex\":50}")).andExpect(status().isBadRequest());
        call(nurse, put("/api/transplants/grafts/" + graft + "/visits/6").contentType(MediaType.APPLICATION_JSON)
                .content("{\"ecd\":1700,\"cv\":42,\"hex\":50,\"visitDate\":\"2026-04-20\"}")).andExpect(status().isOk());
        call(nurse, put("/api/transplants/grafts/" + graft + "/visits/12").contentType(MediaType.APPLICATION_JSON)
                .content("{\"ecd\":1000,\"cv\":46,\"hex\":45}"))
                .andExpect(jsonPath("$.visits", hasSize(2)))
                .andExpect(jsonPath("$.missing", hasSize(0)));
        call(nurse, put("/api/transplants/grafts/" + graft).contentType(MediaType.APPLICATION_JSON)
                .content("{\"rejectionBy12m\":true}")).andExpect(jsonPath("$.rejectionBy12m").value(true));

        call(nurse, post("/api/transplants/grafts/" + graft + "/followups"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.alert").value("red"))
                .andExpect(jsonPath("$.request.graftId").value(graft))
                .andExpect(jsonPath("$.request.donorAge").value(54.0))
                .andExpect(jsonPath("$.request.baselineEcd").value(2400.0))
                .andExpect(jsonPath("$.request.visit12m.ecd").value(1000.0))
                .andExpect(jsonPath("$.request.visit3m").doesNotExist());

        ArgumentCaptor<FollowupRequest> sent = ArgumentCaptor.forClass(FollowupRequest.class);
        verify(mlServiceClient).recommendFollowup(sent.capture());
        assertThat(sent.getValue().rejectionBy12m()).isTrue();
        assertThat(sent.getValue().toString()).doesNotContain("1265");

        String list = call(nurse, get("/api/transplants/grafts/" + graft + "/followups"))
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].alert").value("red"))
                .andReturn().getResponse().getContentAsString();
        String runId = list.replaceAll(".*\"runId\":\"([0-9a-f-]{36})\".*", "$1");
        call(nurse, get("/api/transplants/grafts/" + graft + "/followups/" + runId))
                .andExpect(jsonPath("$.request.baselineEcd").value(2400.0))
                .andExpect(jsonPath("$.result.nextVisitMonths").value(3));
        call(nurse, get("/api/transplants/grafts").param("caseId", caseId))
                .andExpect(jsonPath("$[0].latestFollowup.alert").value("red"));

        AppUser admin = createUser("admin.transplant", RoleName.ADMIN);
        call(admin, get("/api/audit").param("subjectId", caseId))
                .andExpect(jsonPath("$[*].action").value(hasItems("GRAFT_ALLOCATE", "GRAFT_UPDATE", "FOLLOWUP_RUN")));
    }

    // ---------------------------------------------------------------- helpers

    private static final String MATCH = """
            {"request":{"requestId":"Q0001","requestedGrade":"A","surgeryType":"PK","urgency":"Routine"},"method":"ml"}""";

    private static String allocate(String caseId) {
        return "{\"caseId\":\"" + caseId + "\",\"requestId\":\"Q0001\",\"procedure\":\"PK\","
                + "\"indication\":\"Fuchs/Endothelial\",\"surgeryDate\":\"2026-10-01\"}";
    }

    private ResultActions call(AppUser user, MockHttpServletRequestBuilder request) throws Exception {
        return mockMvc.perform(request.header(HttpHeaders.AUTHORIZATION, bearer(user)));
    }

    private String caseWithDetails(String tissueId, LocalDate preserved) throws Exception {
        String id = call(doctor, post("/api/cases").contentType(MediaType.APPLICATION_JSON)
                .content("{\"tissueId\":\"" + tissueId + "\"}")).andReturn().getResponse().getContentAsString()
                .replaceAll(".*\"id\":\"([0-9a-f-]{36})\".*", "$1");
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON)
                .content("{\"donorAgeYears\":54,\"ecd\":2500,\"cv\":32,\"hexPercent\":58,\"deathToPreservationHours\":6,"
                        + "\"preservationDate\":\"" + preserved + "\"}"))
                .andExpect(status().isOk());
        return id;
    }

    private String signedOffCase(String tissueId, LocalDate preserved, String hbv) throws Exception {
        String id = caseWithDetails(tissueId, preserved);
        call(doctor, put("/api/cases/" + id + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\",\"hbv\":\"" + hbv + "\",\"hcv\":\"Negative\",\"syphilis\":\"Negative\"}"))
                .andExpect(status().isOk());
        call(doctor, post("/api/cases/" + id + "/signoffs").contentType(MediaType.APPLICATION_JSON)
                .content("{\"confirmedGrade\":\"A\",\"diseaseFinding\":\"Normal\",\"ecd\":2400,\"cv\":30,\"hexPercent\":60}"))
                .andExpect(status().isCreated());
        return id;
    }
}
