package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.EcdBand;
import com.cornealai.backend.analysis.dto.EcdReference;
import com.cornealai.backend.analysis.dto.grading.FeatureContribution;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.dto.grading.GradingExplanation;
import com.cornealai.backend.analysis.dto.grading.ImageAttributionMap;
import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import com.cornealai.backend.analysis.repository.GradingAnalysisRunRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GradingAnalysisIntegrationTests extends IntegrationTestSupport {

    private static final String FEATURES = "{\"ECD_CD_cells_per_mm2\":2400,\"Stroma_Has_Scar\":null}";

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private GradingAnalysisRunRepository runs;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.grading", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    @Test
    void gradingSendsStoredBytesAndRecordsTheRun() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString())).thenReturn(completed());

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.grade").value("A"))
                .andExpect(jsonPath("$.ecdReference.grade").value("A"))
                .andExpect(jsonPath("$.explanation.imageMap.supportingPng").value("iVBORw0KGgo="));

        verify(mlServiceClient).analyzeGrading(anyString(), contains("\"Stroma_Has_Scar\":null"), eq(image()), anyString());  // decrypted, as uploaded
        GradingAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("completed");
        // Linked to the donor case by UUID; the tissue ID is not stored in the run.
        assertThat(run.getDonorCaseId()).isNotNull();
        assertThat(run.getCaseId()).isEqualTo(run.getDonorCaseId().toString());
        assertThat(run.getResultJson()).doesNotContain("12656R");
        assertThat(run.getGrade()).isEqualTo("A");
        assertThat(run.getEcd()).isEqualTo(2400.0);
        assertThat(run.getClinicalFeaturesJson()).contains("\"ECD_CD_cells_per_mm2\":2400");
        assertThat(run.getResultJson()).contains("\"grade\":\"A\"", "\"contribution\":0.3")
                .doesNotContain("iVBORw0KGgo");
    }

    @Test
    void mlServiceRejectionIsRecordedAndReturnedWithItsCode() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString()))
                .thenThrow(new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "INVALID_FEATURE_TYPE", "CV",
                        "CV must be a number (%).", Map.of("CV", "CV must be a number (%).")));

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("INVALID_FEATURE_TYPE"))
                .andExpect(jsonPath("$.fieldErrors.CV").value("CV must be a number (%)."));
        GradingAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("rejected");
        assertThat(run.getErrorCode()).isEqualTo("INVALID_FEATURE_TYPE");
        assertThat(run.getGrade()).isNull();
    }

    @Test
    void responseWithoutAGradeIsRejected() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        GradingAnalyzeResponse noGrade = new GradingAnalyzeResponse(null, "12656R", "completed", null, null, null,
                null, null, null, null, null, null, null, null);
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString())).thenReturn(noGrade);

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("MODEL_INFERENCE_FAILED"));
    }

    @Test
    void onlyTheUploaderMayGradeAnImage() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        AppUser other = createUser("dr.other.grading", RoleName.DOCTOR);

        analyze(other, "12656R", imageId)
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("TISSUE_ACCESS_DENIED"));
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void nonClinicalRoleCannotRunGrading() throws Exception {
        AppUser support = createUser("support.grading", RoleName.SUPPORT_STAFF);
        analyze(support, "12656R", UUID.randomUUID()).andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    private static GradingAnalyzeResponse completed() {
        EcdReference reference = new EcdReference("completed", "A", "ecd_threshold_tree", 2400.0,
                new EcdBand(2232.0, 2497.0), Map.of("A", 0.9, "B", 0.1), 94, false, "Grade based on ECD only.");
        return new GradingAnalyzeResponse(null, "12656R", "completed", null, "A", "hybrid_random_forest_24_resnet50",
                Map.of("A+", 0.1, "A", 0.7, "B", 0.2), Map.of("ECD_CD_cells_per_mm2", 2400.0),
                List.of("Stroma_Has_Scar"), List.of(), reference, false, "Specialist confirmation required.",
                new GradingExplanation("tree_shap_path_dependent", "A", 0.35, 0.7,
                        List.of(new FeatureContribution("ECD_CD_cells_per_mm2", 2400.0, 0.3)), 0.05,
                        new ImageAttributionMap("shap_weighted_layer4_map", "iVBORw0KGgo=", null, 0.08, -0.03, 0.95),
                        "Explains the model, not the cornea."));
    }

    private UUID uploadedImage(AppUser user, String caseId) throws Exception {
        String body = mockMvc.perform(multipart("/api/analysis/images")
                        .file(new MockMultipartFile("file", "image.jpg", "image/jpeg", image()))
                        .param("caseId", caseId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(user)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return UUID.fromString(body.replaceAll(".*\"imageId\":\"([0-9a-f-]{36})\".*", "$1"));
    }

    private ResultActions analyze(AppUser user, String caseId, UUID imageId) throws Exception {
        return mockMvc.perform(post("/api/analysis/grading")
                .header(HttpHeaders.AUTHORIZATION, bearer(user))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"caseId\":\"%s\",\"imageId\":\"%s\",\"clinicalFeatures\":%s}"
                        .formatted(caseId, imageId, FEATURES)));
    }

    private static byte[] image() throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, "jpeg", out);
        return out.toByteArray();
    }
}
