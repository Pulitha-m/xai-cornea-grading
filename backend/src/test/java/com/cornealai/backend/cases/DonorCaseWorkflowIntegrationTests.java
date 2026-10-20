package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.cases.service.DonorCaseService;
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
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Tissue IDs end to end: one donor case per ID, found by blind index, never stored or sent in plain text. */
class DonorCaseWorkflowIntegrationTests extends IntegrationTestSupport {

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private AnalysisImageRepository images;

    @Autowired
    private DonorCaseRepository cases;

    @Autowired
    private DonorCaseService donorCases;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private jakarta.persistence.EntityManager entityManager;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.cases", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    @Test
    void sameTissueIdSharesOneCaseAndEachEyeIsItsOwnCase() throws Exception {
        AnalysisImage first = images.findById(uploadedImage(" 12656r ")).orElseThrow();
        AnalysisImage second = images.findById(uploadedImage("12656R")).orElseThrow();
        AnalysisImage otherEye = images.findById(uploadedImage("12656L")).orElseThrow();

        assertThat(second.getDonorCaseId()).isEqualTo(first.getDonorCaseId());
        assertThat(otherEye.getDonorCaseId()).isNotEqualTo(first.getDonorCaseId());
        assertThat(cases.count()).isEqualTo(2);
    }

    @Test
    void invalidTissueIdsAreRejectedBeforeAnythingIsStored() throws Exception {
        for (String bad : new String[]{"1265R", "126567R", "12656X", "12656 R", "NEB-2021-12656R", "CASE-001"}) {
            upload(bad)
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_TISSUE_ID"));
        }
        verify(storage, never()).store(anyString(), any(), anyString());
        assertThat(cases.count()).isZero();
        assertThat(images.count()).isZero();
    }

    @Test
    void storageFailureCreatesNoCase() throws Exception {
        doThrow(new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null, "x"))
                .when(storage).store(anyString(), any(), anyString());

        upload("12656R").andExpect(status().isBadGateway());
        assertThat(cases.count()).isZero();
    }

    @Test
    void tissueIdIsNeverStoredInPlainTextNorSentToTheMlService() throws Exception {
        UUID imageId = uploadedImage("12656R");
        UUID caseId = images.findById(imageId).orElseThrow().getDonorCaseId();
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString())).thenReturn(graded());

        grade("12656r", imageId)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("12656R"));  // shown back to the user who entered it

        ArgumentCaptor<String> sentCaseId = ArgumentCaptor.forClass(String.class);
        verify(mlServiceClient).analyzeGrading(sentCaseId.capture(), anyString(), any(), anyString());
        assertThat(sentCaseId.getValue()).isEqualTo(caseId.toString());

        entityManager.flush();
        for (String table : new String[]{"donor_cases", "analysis_images", "grading_analysis_runs"}) {
            var rows = jdbc.queryForList("SELECT * FROM " + table);
            assertThat(rows).as(table).hasSize(1);
            for (var row : rows) {
                for (Object value : row.values()) {
                    String text = value instanceof byte[] bytes
                            ? new String(bytes, StandardCharsets.ISO_8859_1) : String.valueOf(value);
                    assertThat(text).as(table).doesNotContain("12656");
                }
            }
        }
        assertThat(jdbc.queryForObject("SELECT donor_case_id FROM grading_analysis_runs", UUID.class)).isEqualTo(caseId);
    }

    @Test
    void imageCannotBeAnalysedUnderAnotherOrUnknownTissueId() throws Exception {
        UUID imageId = uploadedImage("12656R");
        uploadedImage("12657L");

        for (String wrong : new String[]{"12657L", "99999R"}) {  // another existing case, and an unknown ID
            grade(wrong, imageId)
                    .andExpect(status().isForbidden())
                    .andExpect(jsonPath("$.code").value("TISSUE_ACCESS_DENIED"))
                    .andExpect(jsonPath("$.message").value("The image belongs to a different case."));
        }
        verify(mlServiceClient, never()).analyzeGrading(any(), any(), any(), any());
    }

    @Test
    void caseIsFoundByBlindIndexAndItsTissueIdDecrypts() throws Exception {
        UUID imageId = uploadedImage("12656R");

        var found = donorCases.find(TissueNumber.parse(" 12656r ")).orElseThrow();
        assertThat(found.getId()).isEqualTo(images.findById(imageId).orElseThrow().getDonorCaseId());
        assertThat(found.getCreatedBy()).isEqualTo(doctor.getId());
        assertThat(donorCases.tissueNumberOf(found).value()).isEqualTo("12656R");
        assertThat(donorCases.find(TissueNumber.parse("12656L"))).isEmpty();
    }

    private ResultActions upload(String tissueId) throws Exception {
        return mockMvc.perform(multipart("/api/analysis/images")
                .file(new MockMultipartFile("file", "image.jpg", "image/jpeg", image()))
                .param("caseId", tissueId)
                .header(HttpHeaders.AUTHORIZATION, bearer(doctor)));
    }

    private UUID uploadedImage(String tissueId) throws Exception {
        String body = upload(tissueId).andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return UUID.fromString(body.replaceAll(".*\"imageId\":\"([0-9a-f-]{36})\".*", "$1"));
    }

    private ResultActions grade(String tissueId, UUID imageId) throws Exception {
        return mockMvc.perform(post("/api/analysis/grading")
                .header(HttpHeaders.AUTHORIZATION, bearer(doctor))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"caseId\":\"%s\",\"imageId\":\"%s\",\"clinicalFeatures\":{\"ECD_CD_cells_per_mm2\":2400}}"
                        .formatted(tissueId, imageId)));
    }

    /** The ML service echoes whatever caseId it was sent; here it wrongly echoes the tissue ID. */
    private static GradingAnalyzeResponse graded() {
        return new GradingAnalyzeResponse(null, "12656R", "completed", null, "A", "hybrid_random_forest_24_resnet50",
                null, null, null, null, null, false, null, null);
    }

    private static byte[] image() throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, "jpeg", out);
        return out.toByteArray();
    }
}
