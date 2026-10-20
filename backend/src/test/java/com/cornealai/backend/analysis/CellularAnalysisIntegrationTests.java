package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.ImageValidation;
import com.cornealai.backend.analysis.dto.cellular.*;
import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import com.cornealai.backend.analysis.repository.CellularAnalysisRunRepository;
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

class CellularAnalysisIntegrationTests extends IntegrationTestSupport {

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private CellularAnalysisRunRepository runs;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.cellular", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    @Test
    void analysisSendsStoredBytesAndRecordsTheNumbersWithoutImages() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(completed(true));

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.biomarkers.cellCount").value(1421))
                .andExpect(jsonPath("$.biomarkers.ecd").value(2824.48))
                .andExpect(jsonPath("$.uncertainty.ecdCi95[0]").value(2785.0))
                .andExpect(jsonPath("$.reliability.yellow").value(64))
                .andExpect(jsonPath("$.images.overlayJpeg").value("/9j/overlay"));

        verify(mlServiceClient).analyzeCellular(anyString(), eq(image()), anyString());  // decrypted, as uploaded
        CellularAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("completed");
        // Linked to the donor case by UUID; the tissue ID is not stored in the run.
        assertThat(run.getDonorCaseId()).isNotNull();
        assertThat(run.getCaseId()).isEqualTo(run.getDonorCaseId().toString());
        assertThat(run.getResultJson()).doesNotContain("12656R");
        assertThat(run.getCellCount()).isEqualTo(1421);
        assertThat(run.getEcd()).isEqualTo(2824.48);
        assertThat(run.getCv()).isEqualTo(27.52);
        assertThat(run.getHex()).isEqualTo(64.59);
        assertThat(run.getReliable()).isTrue();
        assertThat(run.getResultJson()).contains("\"cellCount\":1421", "\"ecdCi95\"")
                .doesNotContain("/9j/overlay", "/9j/reliability");
    }

    @Test
    void notReliableResultIsStillReturnedAndRecorded() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(completed(false));

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reliable").value(false))
                .andExpect(jsonPath("$.qualityFlags[0].code").value("too_few_cells"));
        assertThat(runs.findByImageId(imageId).getFirst().getReliable()).isFalse();
    }

    @Test
    void mlServiceRejectionIsRecordedAndReturnedWithItsCode() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString()))
                .thenThrow(new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "INVALID_IMAGE_DOMAIN", "image",
                        "Upload a specular microscopy image showing corneal endothelial cells."));

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("INVALID_IMAGE_DOMAIN"));
        CellularAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("rejected");
        assertThat(run.getErrorCode()).isEqualTo("INVALID_IMAGE_DOMAIN");
        assertThat(run.getEcd()).isNull();
    }

    @Test
    void responseWithoutBiomarkersIsRejected() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        CellularAnalyzeResponse empty = new CellularAnalyzeResponse(null, "12656R", "completed", null, null, null,
                null, null, null, null, null, null, null, null, null, null, null);
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(empty);

        analyze(doctor, "12656R", imageId)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("MODEL_INFERENCE_FAILED"));
        assertThat(runs.findByImageId(imageId).getFirst().getStatus()).isEqualTo("rejected");
    }

    @Test
    void anotherClinicianCanAnalyseTheCase() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        AppUser other = createUser("dr.other.cellular", RoleName.DOCTOR);

        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(completed(true));

        analyze(other, "12656R", imageId).andExpect(status().isOk());
        assertThat(runs.findByImageId(imageId).getFirst().getRequestedBy()).isEqualTo(other.getId());
    }

    @Test
    void imageOfAnotherCaseIsRefused() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        analyze(doctor, "12657L", imageId)
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("TISSUE_ACCESS_DENIED"));
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void nonClinicalRoleCannotRunCellularAnalysis() throws Exception {
        AppUser support = createUser("support.cellular", RoleName.SUPPORT_STAFF);
        analyze(support, "12656R", UUID.randomUUID()).andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    private static CellularAnalyzeResponse completed(boolean reliable) {
        CellularBiomarkers bm = new CellularBiomarkers(reliable ? 1421 : 12, 2824.48, 354.04, 97.42, 27.52, 64.59, 1087,
                0.887, 0.035, 3.97, Map.of("p5", 214.2, "p50", 347.2, "p95", 524.6),
                Map.of("<=4", 0.9, "5", 20.2, "6", 64.59, "7", 13.9, ">=8", 0.4), 1);
        List<QualityFlag> flags = reliable ? List.of()
                : List.of(new QualityFlag("error", "too_few_cells", "only 12 complete cells (< 30): biomarkers not reliable"));
        return new CellularAnalyzeResponse(null, "12656R", "completed", "Research tool for a specialist.",
                new ImageValidation("VALID_CORNEAL_IMAGE", true, 1296, 972, "JPEG"),
                "roi_efficientnet_b0_stardist_onnx_v1", 0.796, true, bm,
                new CellularRoi("cnn", 0.72, 0.78, 0.78), flags, reliable,
                new CellularUncertainty("95 % CI", List.of(2785.0, 2865.4), List.of(25.97, 29.09), List.of(61.3, 67.7)),
                new CellularEvidence(5.0, 36.5), new CellularReliability("rule", 1351, 64, 6, 0.904),
                new CellularImages("/9j/overlay", "/9j/reliability", "/9j/cv"), 7.4);
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
        return mockMvc.perform(post("/api/analysis/cellular")
                .header(HttpHeaders.AUTHORIZATION, bearer(user))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"caseId\":\"%s\",\"imageId\":\"%s\"}".formatted(caseId, imageId)));
    }

    private static byte[] image() throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, "jpeg", out);
        return out.toByteArray();
    }
}
