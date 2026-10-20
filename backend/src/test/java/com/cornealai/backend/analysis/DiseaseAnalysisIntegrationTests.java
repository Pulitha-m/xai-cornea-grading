package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.disease.CellChekReport;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.DiseaseFinding;
import com.cornealai.backend.analysis.dto.disease.GradcamFocus;
import com.cornealai.backend.analysis.dto.disease.InputCheck;
import com.cornealai.backend.analysis.dto.disease.InputIssue;
import com.cornealai.backend.analysis.entity.DiseaseAnalysisRun;
import com.cornealai.backend.analysis.repository.DiseaseAnalysisRunRepository;
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
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DiseaseAnalysisIntegrationTests extends IntegrationTestSupport {

    private static final String MEASUREMENTS =
            "{\"ECD_CD_cells_per_mm2\":2650,\"SD\":143,\"CV\":38,\"HEX_percent\":55,\"Donor_Age\":null}";

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private DiseaseAnalysisRunRepository runs;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.disease", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    @Test
    void analysisSendsStoredBytesAndRecordsTheRunWithoutGradcam() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeDisease(anyString(), anyString(), eq(false), any(), anyString()))
                .thenReturn(completed());

        analyze(doctor, "12656R", imageId, false)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.detected[0]").value("FECD"))
                .andExpect(jsonPath("$.diseases[0].gradcamPng").value("iVBORw0KGgo="));

        verify(mlServiceClient).analyzeDisease(anyString(), contains("\"Donor_Age\":null"), eq(false), eq(image()), anyString());  // decrypted, as uploaded
        DiseaseAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("completed");
        // Linked to the donor case by UUID; the tissue ID is not stored in the run.
        assertThat(run.getDonorCaseId()).isNotNull();
        assertThat(run.getCaseId()).isEqualTo(run.getDonorCaseId().toString());
        assertThat(run.getResultJson()).doesNotContain("12656R");
        assertThat(run.isForced()).isFalse();
        assertThat(run.getMeasurementsJson()).contains("\"ECD_CD_cells_per_mm2\":2650");
        assertThat(run.getResultJson()).contains("\"detected\":[\"FECD\"]").contains("\"region\":\"lower right\"")
                .doesNotContain("iVBORw0KGgo");
    }

    @Test
    void failedInputChecksAreReturnedAndRecorded() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        InputCheck check = new InputCheck(false, false,
                List.of(new InputIssue("VALUE_NOT_POSSIBLE", "ECD_CD_cells_per_mm2", "ECD = 0: zero or negative is impossible.")),
                List.of(new InputIssue("VALUE_MISSING", "Donor_Age", "Donor age not recorded.")));
        when(mlServiceClient.analyzeDisease(anyString(), anyString(), anyBoolean(), any(), anyString()))
                .thenReturn(DiseaseAnalyzeResponse.inputCheckFailed("12656R", "The inputs did not pass the checks.", check, null));

        analyze(doctor, "12656R", imageId, false)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("input_check_failed"))
                .andExpect(jsonPath("$.inputCheck.errors[0].field").value("ECD_CD_cells_per_mm2"))
                .andExpect(jsonPath("$.inputCheck.warnings[0].code").value("VALUE_MISSING"));
        assertThat(runs.findByImageId(imageId).getFirst().getStatus()).isEqualTo("input_check_failed");
    }

    @Test
    void forceIsPassedOnAndRecorded() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeDisease(anyString(), anyString(), eq(true), any(), anyString())).thenReturn(completed());

        analyze(doctor, "12656R", imageId, true).andExpect(status().isOk());
        assertThat(runs.findByImageId(imageId).getFirst().isForced()).isTrue();
    }

    @Test
    void mlServiceRejectionIsRecordedAndReturnedWithItsCode() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyzeDisease(anyString(), anyString(), anyBoolean(), any(), anyString()))
                .thenThrow(new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "INVALID_IMAGE_DOMAIN", "image",
                        "Upload a specular microscopy image showing corneal endothelial cells."));

        analyze(doctor, "12656R", imageId, false)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("INVALID_IMAGE_DOMAIN"));
        DiseaseAnalysisRun run = runs.findByImageId(imageId).getFirst();
        assertThat(run.getStatus()).isEqualTo("rejected");
        assertThat(run.getErrorCode()).isEqualTo("INVALID_IMAGE_DOMAIN");
    }

    @Test
    void anotherClinicianCanAnalyseTheCase() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        AppUser other = createUser("dr.other", RoleName.DOCTOR);

        when(mlServiceClient.analyzeDisease(anyString(), anyString(), eq(false), any(), anyString())).thenReturn(completed());

        analyze(other, "12656R", imageId, false).andExpect(status().isOk());
        assertThat(runs.findByImageId(imageId).getFirst().getRequestedBy()).isEqualTo(other.getId());
    }

    @Test
    void nonClinicalRoleCannotRunDiseaseAnalysis() throws Exception {
        AppUser support = createUser("support.disease", RoleName.SUPPORT_STAFF);
        analyze(support, "12656R", UUID.randomUUID(), false).andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void reportIsReadThroughMlServiceAndNotStored() throws Exception {
        CellChekReport reading = new CellChekReport("image",
                Map.of("ECD_CD_cells_per_mm2", 2016.0, "SD", 175.0, "CV", 35.0, "HEX_percent", 48.0, "Donor_Age", 59.0),
                List.of(), "NEB-TEST L", "OS", 124.0, 61468.0, List.of());
        when(mlServiceClient.readCellChekReport(any(), anyString())).thenReturn(reading);

        mockMvc.perform(multipart("/api/analysis/disease/report")
                        .file(new MockMultipartFile("file", "report.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(doctor)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.values.ECD_CD_cells_per_mm2").value(2016.0))
                .andExpect(jsonPath("$.tissueId").value("NEB-TEST L"));
        verify(storage, never()).store(anyString(), any(), anyString());
        assertThat(runs.count()).isZero();
    }

    @Test
    void nonClinicalRoleCannotReadReports() throws Exception {
        AppUser support = createUser("support.report", RoleName.SUPPORT_STAFF);
        mockMvc.perform(multipart("/api/analysis/disease/report")
                        .file(new MockMultipartFile("file", "report.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(support)))
                .andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void reportIsReadThroughMlServiceAndNotStored() throws Exception {
        CellChekReport reading = new CellChekReport("image",
                Map.of("ECD_CD_cells_per_mm2", 2016.0, "SD", 175.0, "CV", 35.0, "HEX_percent", 48.0, "Donor_Age", 59.0),
                List.of(), "NEB-TEST L", "OS", 124.0, 61468.0, List.of());
        when(mlServiceClient.readCellChekReport(any(), anyString())).thenReturn(reading);

        mockMvc.perform(multipart("/api/analysis/disease/report")
                        .file(new MockMultipartFile("file", "report.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(doctor)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.values.ECD_CD_cells_per_mm2").value(2016.0))
                .andExpect(jsonPath("$.tissueId").value("NEB-TEST L"));
        verify(storage, never()).store(anyString(), any(), anyString());
        assertThat(runs.count()).isZero();
    }

    @Test
    void nonClinicalRoleCannotReadReports() throws Exception {
        AppUser support = createUser("support.report", RoleName.SUPPORT_STAFF);
        mockMvc.perform(multipart("/api/analysis/disease/report")
                        .file(new MockMultipartFile("file", "report.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(support)))
                .andExpect(status().isForbidden());
        verifyNoInteractions(mlServiceClient);
    }

    private static DiseaseAnalyzeResponse completed() {
        List<DiseaseFinding> findings = List.of(
                new DiseaseFinding("FECD", "FECD", 0.8, 0.23, true, "iVBORw0KGgo="),
                new DiseaseFinding("Guttata", "Guttata", 0.1, 0.44, false, null));
        return new DiseaseAnalyzeResponse(null, "CASE-1", "completed", "Research tool, not a medical diagnosis.",
                null, new InputCheck(true, false, List.of(), List.of()), null, "densenet121_image_numbers_fusion_v2",
                findings, List.of("FECD"), false, List.of(), "Mild", Map.of("FECDgroup", 0.3), Map.of(), List.of(), true);
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

    private ResultActions analyze(AppUser user, String caseId, UUID imageId, boolean force) throws Exception {
        return mockMvc.perform(post("/api/analysis/disease")
                .header(HttpHeaders.AUTHORIZATION, bearer(user))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"caseId\":\"%s\",\"imageId\":\"%s\",\"measurements\":%s,\"force\":%s}"
                        .formatted(caseId, imageId, MEASUREMENTS, force)));
    }

    private static byte[] image() throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, "jpeg", out);
        return out.toByteArray();
    }
}
