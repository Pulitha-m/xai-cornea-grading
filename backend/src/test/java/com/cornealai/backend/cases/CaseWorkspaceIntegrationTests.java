package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.EcdBand;
import com.cornealai.backend.analysis.dto.EcdReference;
import com.cornealai.backend.analysis.dto.ImageValidation;
import com.cornealai.backend.analysis.dto.cellular.*;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.DiseaseFinding;
import com.cornealai.backend.analysis.dto.disease.InputCheck;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.repository.CellularAnalysisRunRepository;
import com.cornealai.backend.analysis.repository.DiseaseAnalysisRunRepository;
import com.cornealai.backend.analysis.repository.GradingAnalysisRunRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** The case workspace end to end: open by tissue ID, details once, images, analyses from the case, history. */
class CaseWorkspaceIntegrationTests extends IntegrationTestSupport {

    private static final String DETAILS = """
            {"donorAgeYears":54,"ecd":2400,"cv":32,"hexPercent":58,"sd":110,"totalCellCount":120,
             "totalAreaUm2":50000,"slitLamp":{"Stroma_Is_Clear":1,"Stroma_Has_Scar":false,
             "Descemet_Fold_Severity":"Mild"}}""";

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private CellularAnalysisRunRepository cellularRuns;

    @Autowired
    private GradingAnalysisRunRepository gradingRuns;

    @Autowired
    private DiseaseAnalysisRunRepository diseaseRuns;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.workspace", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    // ---------------------------------------------------------------- cases

    @Test
    void caseIsOpenedOnceByTissueIdAndFoundAgain() throws Exception {
        String id = caseId("12656R");
        call(doctor, post("/api/cases").contentType(MediaType.APPLICATION_JSON).content("{\"tissueId\":\" 12656r \"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id))
                .andExpect(jsonPath("$.tissueId").value("12656R"));

        call(doctor, get("/api/cases").param("tissueId", "12656R")).andExpect(jsonPath("$[0].id").value(id));
        call(doctor, get("/api/cases")).andExpect(jsonPath("$", hasSize(1)));
        call(doctor, get("/api/cases").param("tissueId", "12657L"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("CASE_NOT_FOUND"));
        call(doctor, post("/api/cases").contentType(MediaType.APPLICATION_JSON).content("{\"tissueId\":\"CASE-1\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("INVALID_TISSUE_ID"));
    }

    @Test
    void nonClinicalRolesCannotUseCases() throws Exception {
        for (RoleName role : List.of(RoleName.MANAGER, RoleName.SUPPORT_STAFF, RoleName.ADMIN)) {
            AppUser user = createUser("user." + role.name().toLowerCase(), role);
            call(user, get("/api/cases")).andExpect(status().isForbidden());
        }
    }

    @Test
    void detailsAreSavedOnceWithValidatedSlitLampFindings() throws Exception {
        String id = caseId("12656R");
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.details.ecd").value(2400.0))
                .andExpect(jsonPath("$.details.slitLamp.Stroma_Is_Clear").value(1))
                .andExpect(jsonPath("$.details.slitLamp.Stroma_Has_Scar").value(0))
                .andExpect(jsonPath("$.details.slitLamp.Descemet_Fold_Severity").value("Mild"))
                .andExpect(jsonPath("$.details.slitLamp.Endo_Has_RBC").doesNotExist());

        for (String bad : List.of("{\"slitLamp\":{\"Unknown_Finding\":1}}", "{\"slitLamp\":{\"Stroma_Is_Clear\":2}}",
                "{\"slitLamp\":{\"Descemet_Fold_Severity\":\"Severe\"}}", "{\"ecd\":-5}", "{\"hexPercent\":120}")) {
            call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(bad))
                    .andExpect(status().isBadRequest());
        }
        call(doctor, get("/api/cases/" + id)).andExpect(jsonPath("$.details.ecd").value(2400.0));
    }

    // ---------------------------------------------------------------- images

    @Test
    void imagesAreStoredEncryptedListedAndViewableOnlyThroughTheirCase() throws Exception {
        String id = caseId("12656R");
        String otherId = caseId("12657L");
        String imageId = uploadImage(id);

        assertThat(stored).isNotEqualTo(image());
        call(doctor, get("/api/cases/" + id + "/images")).andExpect(jsonPath("$[0].id").value(imageId));
        call(doctor, get("/api/cases/" + id + "/images/" + imageId + "/content"))
                .andExpect(status().isOk())
                .andExpect(content().contentType("image/jpeg"))
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(content().bytes(image()));
        call(doctor, get("/api/cases/" + otherId + "/images/" + imageId + "/content"))
                .andExpect(status().isNotFound());
        call(doctor, get("/api/cases/" + id)).andExpect(jsonPath("$.imageCount").value(1));
    }

    // ---------------------------------------------------------------- analyses

    @Test
    void modulesRunOnTheCaseWithInputsFromItsDetailsAndAreLinked() throws Exception {
        String id = caseId("12656R");
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS));
        String imageId = uploadImage(id);
        stubAllModules();

        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"disease\",\"grading\",\"cellular\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tissueId").value("12656R"))
                .andExpect(jsonPath("$.modules.cellular.status").value("completed"))
                .andExpect(jsonPath("$.modules.grading.status").value("completed"))
                .andExpect(jsonPath("$.modules.grading.result.grade").value("A"))
                .andExpect(jsonPath("$.modules.grading.result.caseId").value("12656R"))
                .andExpect(jsonPath("$.modules.disease.status").value("completed"))
                .andExpect(jsonPath("$.consistency[*].code").value(org.hamcrest.Matchers.containsInAnyOrder(
                        "GRADE_DIFFERS_FROM_ECD_REFERENCE", "DISEASE_WITH_HIGH_GRADE")));

        ArgumentCaptor<String> features = ArgumentCaptor.forClass(String.class);
        verify(mlServiceClient).analyzeGrading(anyString(), features.capture(), any(), anyString());
        assertThat(features.getValue()).contains("\"ECD_CD_cells_per_mm2\":2400.0", "\"Stroma_Is_Clear\":1",
                "\"Descemet_Fold_Severity\":\"Mild\"", "\"Endo_Has_RBC\":null");
        ArgumentCaptor<String> measurements = ArgumentCaptor.forClass(String.class);
        verify(mlServiceClient).analyzeDisease(anyString(), measurements.capture(), anyBoolean(), any(), anyString());
        assertThat(measurements.getValue()).contains("\"Donor_Age\":54", "\"HEX_percent\":58.0");

        UUID caseUuid = UUID.fromString(id);
        UUID analysisId = gradingRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseUuid).getFirst().getCaseAnalysisId();
        assertThat(analysisId).isNotNull();
        assertThat(cellularRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseUuid).getFirst().getCaseAnalysisId())
                .isEqualTo(analysisId);
        assertThat(diseaseRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseUuid).getFirst().getCaseAnalysisId())
                .isEqualTo(analysisId);
    }

    @Test
    void missingDetailsOrAFailingModuleNeverHideTheOtherResults() throws Exception {
        String id = caseId("12656R");
        String imageId = uploadImage(id);
        stubAllModules();

        // No details yet: grading and disease cannot run, cellular still does.
        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"cellular\",\"grading\",\"disease\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.modules.cellular.status").value("completed"))
                .andExpect(jsonPath("$.modules.grading.status").value("rejected"))
                .andExpect(jsonPath("$.modules.grading.errorCode").value("CASE_DETAILS_MISSING"))
                .andExpect(jsonPath("$.modules.disease.errorCode").value("CASE_DETAILS_MISSING"));

        // An unexpected failure in grading is recorded as "failed"; disease still completes.
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS));
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString()))
                .thenThrow(new IllegalStateException("boom"));
        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"grading\",\"disease\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.modules.grading.status").value("failed"))
                .andExpect(jsonPath("$.modules.grading.message").value(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("boom"))))
                .andExpect(jsonPath("$.modules.disease.status").value("completed"));
        assertThat(gradingRuns.findByDonorCaseIdOrderByCreatedAtDesc(UUID.fromString(id)))
                .singleElement().satisfies(run -> {
                    assertThat(run.getStatus()).isEqualTo("failed");
                    assertThat(run.getErrorCode()).isEqualTo("INTERNAL_ERROR");
                });
    }

    @Test
    void imageOfAnotherCaseAndUnknownModulesAreRefused() throws Exception {
        String id = caseId("12656R");
        String otherImage = uploadImage(caseId("12657L"));

        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + otherImage + "\",\"modules\":[\"cellular\"]}"))
                .andExpect(status().isNotFound());
        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + otherImage + "\",\"modules\":[\"recommendation\"]}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(mlServiceClient);
    }

    // ---------------------------------------------------------------- history

    @Test
    void historyListsEveryRunNewestFirstAndAnotherClinicianSeesIt() throws Exception {
        String id = caseId("12656R");
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS));
        String imageId = uploadImage(id);
        stubAllModules();
        call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"cellular\",\"grading\",\"disease\"]}"));

        AppUser nurse = createUser("nurse.workspace", RoleName.NURSE);
        String body = call(nurse, get("/api/cases/" + id + "/runs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(3)))
                .andExpect(jsonPath("$[?(@.module == 'grading')].headline.grade").value("A"))
                .andExpect(jsonPath("$[?(@.module == 'cellular')].headline.ecd").value(2824.48))
                .andExpect(jsonPath("$[?(@.module == 'disease')].headline.detected[0]").value("FECD"))
                .andReturn().getResponse().getContentAsString();

        String gradingRun = body.replaceAll(".*\"id\":\"([0-9a-f-]{36})\",\"module\":\"grading\".*", "$1");
        call(nurse, get("/api/cases/" + id + "/runs/grading/" + gradingRun))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.inputs.ECD_CD_cells_per_mm2").value(2400.0))
                .andExpect(jsonPath("$.result.grade").value("A"));
        call(nurse, get("/api/cases/" + caseId("12657L") + "/runs/grading/" + gradingRun))
                .andExpect(status().isNotFound());
    }

    @Test
    void modulePagesListEarlierResultsAcrossCasesSearchableByTissueIdAndPagedBack() throws Exception {
        stubAllModules();
        for (String tissue : List.of("12656R", "12657L", "12658R")) {
            String id = caseId(tissue);
            call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS));
            String imageId = uploadImage(id);
            call(doctor, post("/api/cases/" + id + "/analyses").contentType(MediaType.APPLICATION_JSON)
                    .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"grading\"]}"))
                    .andExpect(status().isOk());
            Thread.sleep(5);  // distinct timestamps for paging
        }
        AppUser nurse = createUser("nurse.modules", RoleName.NURSE);

        call(nurse, get("/api/cases/runs").param("module", "grading"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(3)))
                .andExpect(jsonPath("$.items[0].tissueId").value("12658R"))
                .andExpect(jsonPath("$.items[0].run.headline.grade").value("A"))
                .andExpect(jsonPath("$.nextBefore").doesNotExist());

        String first = call(nurse, get("/api/cases/runs").param("module", "grading").param("limit", "2"))
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andExpect(jsonPath("$.nextBefore").isNotEmpty())
                .andReturn().getResponse().getContentAsString();
        String nextBefore = first.replaceAll(".*\"nextBefore\":\"([^\"]+)\".*", "$1");
        call(nurse, get("/api/cases/runs").param("module", "grading").param("limit", "2").param("before", nextBefore))
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].tissueId").value("12656R"))
                .andExpect(jsonPath("$.nextBefore").doesNotExist());

        call(nurse, get("/api/cases/runs").param("module", "grading").param("tissueId", " 12657l "))
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].tissueId").value("12657L"));
        call(nurse, get("/api/cases/runs").param("module", "grading").param("tissueId", "99999R"))
                .andExpect(jsonPath("$.items", hasSize(0)));
        call(nurse, get("/api/cases/runs").param("module", "cellular")).andExpect(jsonPath("$.items", hasSize(0)));
        call(nurse, get("/api/cases/runs").param("module", "recommendation")).andExpect(status().isBadRequest());
        call(nurse, get("/api/cases/runs").param("module", "grading").param("tissueId", "CASE-1"))
                .andExpect(status().isBadRequest());
        call(createUser("manager.modules", RoleName.MANAGER), get("/api/cases/runs").param("module", "grading"))
                .andExpect(status().isForbidden());
    }

    // ---------------------------------------------------------------- helpers

    private ResultActions call(AppUser user, MockHttpServletRequestBuilder request) throws Exception {
        return mockMvc.perform(request.header(HttpHeaders.AUTHORIZATION, bearer(user)));
    }

    private String caseId(String tissueId) throws Exception {
        String body = call(doctor, post("/api/cases").contentType(MediaType.APPLICATION_JSON)
                .content("{\"tissueId\":\"" + tissueId + "\"}"))
                .andReturn().getResponse().getContentAsString();
        return body.replaceAll(".*\"id\":\"([0-9a-f-]{36})\".*", "$1");
    }

    private String uploadImage(String caseId) throws Exception {
        String body = mockMvc.perform(multipart("/api/cases/" + caseId + "/images")
                        .file(new MockMultipartFile("file", "image.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(doctor)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return body.replaceAll(".*\"imageId\":\"([0-9a-f-]{36})\".*", "$1");
    }

    private void stubAllModules() {
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(cellular());
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString())).thenReturn(graded());
        when(mlServiceClient.analyzeDisease(anyString(), anyString(), anyBoolean(), any(), anyString()))
                .thenReturn(diseased());
    }

    private static CellularAnalyzeResponse cellular() {
        CellularBiomarkers bm = new CellularBiomarkers(1421, 2824.48, 354.04, 97.42, 27.52, 64.59, 1087,
                0.887, 0.035, 3.97, Map.of(), Map.of(), 1);
        return new CellularAnalyzeResponse(null, null, "completed", null,
                new ImageValidation("VALID_CORNEAL_IMAGE", true, 1296, 972, "JPEG"), "stardist", 0.796, true, bm,
                null, List.of(), true, null, null, null, null, 7.4);
    }

    /** Grade A while the ECD reference says B: one consistency flag. */
    private static GradingAnalyzeResponse graded() {
        EcdReference reference = new EcdReference("completed", "B", "ecd_threshold_tree", 2400.0,
                new EcdBand(2232.0, 2497.0), Map.of("B", 1.0), 94, false, null);
        return new GradingAnalyzeResponse(null, null, "completed", null, "A", "hybrid_random_forest_24_resnet50",
                Map.of("A", 0.7), null, null, List.of(), reference, false, null, null);
    }

    /** FECD detected: with grade A, the second consistency flag. */
    private static DiseaseAnalyzeResponse diseased() {
        return new DiseaseAnalyzeResponse(null, null, "completed", null, null,
                new InputCheck(true, false, List.of(), List.of()), null, "densenet121_image_numbers_fusion_v2",
                List.of(new DiseaseFinding("FECD", "FECD", 0.8, 0.23, true, null)), List.of("FECD"), false,
                List.of(), "Mild", Map.of(), Map.of(), List.of(), true);
    }

    private static byte[] image() throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, "jpeg", out);
        return out.toByteArray();
    }
}
