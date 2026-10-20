package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.EcdBand;
import com.cornealai.backend.analysis.dto.EcdReference;
import com.cornealai.backend.analysis.dto.ImageValidation;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.cellular.CellularBiomarkers;
import com.cornealai.backend.analysis.dto.cellular.CellularImages;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.dto.grading.GradingExplanation;
import com.cornealai.backend.analysis.dto.grading.ImageAttributionMap;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Result images kept encrypted, specialist sign-off, serology (doctors only) and the audit log. */
class SignoffSerologyAuditIntegrationTests extends IntegrationTestSupport {

    private static final String DETAILS = "{\"donorAgeYears\":54,\"ecd\":2400,\"cv\":32,\"hexPercent\":58,"
            + "\"deathToPreservationHours\":6,\"preservationDate\":\"2026-10-15\"}";

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private EntityManager entityManager;

    private final Map<String, byte[]> bucket = new HashMap<>();
    private AppUser doctor;
    private AppUser nurse;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.signoff", RoleName.DOCTOR);
        nurse = createUser("nurse.signoff", RoleName.NURSE);
        when(storage.bucket()).thenReturn("specular-images");
        doAnswer(invocation -> {
            bucket.put(invocation.getArgument(0), invocation.getArgument(1));
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> bucket.get(invocation.<String>getArgument(0)));
    }

    // ---------------------------------------------------------------- result images

    @Test
    void resultImagesAreStoredEncryptedAndPutBackWhenTheRunIsOpened() throws Exception {
        String caseId = caseWithDetails("12656R");
        String imageId = uploadImage(caseId);
        String png = Base64.getEncoder().encodeToString(png());
        String jpeg = Base64.getEncoder().encodeToString(image());
        when(mlServiceClient.analyzeGrading(anyString(), anyString(), any(), anyString())).thenReturn(graded(png));
        when(mlServiceClient.analyzeCellular(anyString(), any(), anyString())).thenReturn(cellular(jpeg));

        call(doctor, post("/api/cases/" + caseId + "/analyses").contentType(MediaType.APPLICATION_JSON)
                .content("{\"imageId\":\"" + imageId + "\",\"modules\":[\"grading\",\"cellular\"]}"))
                .andExpect(status().isOk());

        // One grading map (the opposing map is empty) and three cellular overlays.
        assertThat(bucket.keySet().stream().filter(k -> k.startsWith("artifacts/"))).hasSize(4);
        byte[] plainPng = png();
        bucket.forEach((path, bytes) -> {
            if (path.startsWith("artifacts/")) {
                assertThat(bytes).isNotEqualTo(plainPng).isNotEqualTo(Base64.getDecoder().decode(jpeg));
            }
        });

        String runs = call(nurse, get("/api/cases/" + caseId + "/runs")).andReturn().getResponse().getContentAsString();
        String gradingRun = runs.replaceAll(".*\"id\":\"([0-9a-f-]{36})\",\"module\":\"grading\".*", "$1");
        String cellularRun = runs.replaceAll(".*\"id\":\"([0-9a-f-]{36})\",\"module\":\"cellular\".*", "$1");

        call(nurse, get("/api/cases/" + caseId + "/runs/grading/" + gradingRun))
                .andExpect(jsonPath("$.result.caseId").value("12656R"))
                .andExpect(jsonPath("$.result.explanation.imageMap.supportingPng").value(png))
                .andExpect(jsonPath("$.result.explanation.imageMap.opposingPng").doesNotExist());
        call(nurse, get("/api/cases/" + caseId + "/runs/cellular/" + cellularRun))
                .andExpect(jsonPath("$.result.images.overlayJpeg").value(jpeg))
                .andExpect(jsonPath("$.result.images.cvEvidenceJpeg").value(jpeg));

        // The stored result JSON itself holds no images.
        entityManager.flush();
        assertThat(jdbc.queryForObject("SELECT result_json FROM grading_analysis_runs", String.class)).doesNotContain(png);
    }

    // ---------------------------------------------------------------- sign-off

    @Test
    void onlyDoctorsSignOffAndNotesAreStoredEncrypted() throws Exception {
        String caseId = caseWithDetails("12656R");
        String body = "{\"confirmedGrade\":\"A\",\"diseaseFinding\":\"Guttata\",\"ecd\":2400,\"cv\":32,"
                + "\"hexPercent\":58,\"notes\":\"Seen by Dr Perera; mild guttata centrally\"}";

        call(nurse, post("/api/cases/" + caseId + "/signoffs").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isForbidden());
        call(doctor, post("/api/cases/" + caseId + "/signoffs").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.confirmedGrade").value("A"))
                .andExpect(jsonPath("$.notes").value("Seen by Dr Perera; mild guttata centrally"));
        call(doctor, post("/api/cases/" + caseId + "/signoffs").contentType(MediaType.APPLICATION_JSON)
                .content("{\"confirmedGrade\":\"A++\",\"diseaseFinding\":\"Guttata\"}"))
                .andExpect(status().isBadRequest());

        call(nurse, get("/api/cases/" + caseId + "/signoffs"))
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].notes").value("Seen by Dr Perera; mild guttata centrally"));
        call(nurse, get("/api/cases/" + caseId))
                .andExpect(jsonPath("$.latestSignoff.confirmedGrade").value("A"))
                .andExpect(jsonPath("$.latestSignoff.diseaseFinding").value("Guttata"));

        byte[] notes = jdbc.queryForObject("SELECT notes_enc FROM case_signoffs", byte[].class);
        assertThat(new String(notes, StandardCharsets.ISO_8859_1)).doesNotContain("Perera");
    }

    // ---------------------------------------------------------------- serology

    @Test
    void serologyIsDoctorsOnlyEncryptedAndDrivesTheClearFlag() throws Exception {
        String caseId = caseWithDetails("12656R");

        call(nurse, get("/api/cases/" + caseId + "/serology")).andExpect(status().isForbidden());
        call(nurse, put("/api/cases/" + caseId + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\"}")).andExpect(status().isForbidden());

        call(doctor, put("/api/cases/" + caseId + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\",\"hbv\":\"Negative\",\"hcv\":\"Negative\",\"syphilis\":\"Negative\"}"))
                .andExpect(jsonPath("$.serologyClear").value(true));
        call(doctor, put("/api/cases/" + caseId + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\",\"hbv\":\"Positive\",\"hcv\":\"Negative\",\"syphilis\":null}"))
                .andExpect(jsonPath("$.serologyClear").value(false));
        call(doctor, get("/api/cases/" + caseId + "/serology"))
                .andExpect(jsonPath("$.hbv").value("Positive"))
                .andExpect(jsonPath("$.syphilis").doesNotExist());
        call(doctor, put("/api/cases/" + caseId + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Maybe\"}")).andExpect(status().isBadRequest());

        entityManager.flush();
        byte[] stored = jdbc.queryForObject("SELECT serology_enc FROM donor_cases", byte[].class);
        assertThat(new String(stored, StandardCharsets.ISO_8859_1)).doesNotContain("Positive", "hbv");
        // The case itself does not reveal serology to clinicians.
        call(nurse, get("/api/cases/" + caseId)).andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("serology"))));
    }

    // ---------------------------------------------------------------- candidates

    @Test
    void signedOffCasesBecomeRecommendationCandidatesWithConfirmedValues() throws Exception {
        String signed = caseWithDetails("12656R");
        caseWithDetails("12657L");  // not signed off: not a candidate
        call(doctor, put("/api/cases/" + signed + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\",\"hbv\":\"Negative\",\"hcv\":\"Negative\",\"syphilis\":\"Negative\"}"));
        call(doctor, post("/api/cases/" + signed + "/signoffs").contentType(MediaType.APPLICATION_JSON)
                .content("{\"confirmedGrade\":\"B\",\"diseaseFinding\":\"Normal\",\"ecd\":2350}"));

        call(nurse, get("/api/cases/candidates")).andExpect(status().isForbidden());
        call(doctor, get("/api/cases/candidates"))
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].recordId").value(signed))
                .andExpect(jsonPath("$[0].tissueId").value("12656R"))
                .andExpect(jsonPath("$[0].grade").value("B"))
                .andExpect(jsonPath("$[0].ecd").value(2350.0))
                .andExpect(jsonPath("$[0].donorAge").value(54.0))
                .andExpect(jsonPath("$[0].deathToPreservationH").value(6.0))
                .andExpect(jsonPath("$[0].serologyClear").value("Yes"))
                .andExpect(jsonPath("$[0].diseaseFinding").value("Normal"));
    }

    // ---------------------------------------------------------------- audit

    @Test
    void decryptionsAreAuditedAndOnlyAdministratorsReadTheLog() throws Exception {
        String caseId = caseWithDetails("12656R");
        String imageId = uploadImage(caseId);
        call(nurse, get("/api/cases/" + caseId));
        call(nurse, get("/api/cases/" + caseId + "/images/" + imageId + "/content"));
        call(doctor, put("/api/cases/" + caseId + "/serology").contentType(MediaType.APPLICATION_JSON)
                .content("{\"hiv\":\"Negative\"}"));
        call(doctor, get("/api/cases/" + caseId + "/serology"));

        AppUser admin = createUser("admin.audit", RoleName.ADMIN);
        call(nurse, get("/api/audit")).andExpect(status().isForbidden());
        call(doctor, get("/api/audit")).andExpect(status().isForbidden());
        String log = call(admin, get("/api/audit").param("subjectId", caseId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].action").value(hasItems("CASE_VIEW", "CASE_UPDATE", "SEROLOGY_UPDATE",
                        "SEROLOGY_VIEW")))
                .andExpect(jsonPath("$[?(@.action == 'SEROLOGY_VIEW')].username").value("dr.signoff"))
                .andReturn().getResponse().getContentAsString();
        assertThat(log).doesNotContain("12656", "Negative");
        call(admin, get("/api/audit").param("subjectId", imageId))
                .andExpect(jsonPath("$[0].action").value("IMAGE_VIEW"))
                .andExpect(jsonPath("$[0].username").value("nurse.signoff"));
    }

    // ---------------------------------------------------------------- helpers

    private ResultActions call(AppUser user, MockHttpServletRequestBuilder request) throws Exception {
        return mockMvc.perform(request.header(HttpHeaders.AUTHORIZATION, bearer(user)));
    }

    private String caseWithDetails(String tissueId) throws Exception {
        String body = call(doctor, post("/api/cases").contentType(MediaType.APPLICATION_JSON)
                .content("{\"tissueId\":\"" + tissueId + "\"}")).andReturn().getResponse().getContentAsString();
        String id = body.replaceAll(".*\"id\":\"([0-9a-f-]{36})\".*", "$1");
        call(doctor, put("/api/cases/" + id + "/details").contentType(MediaType.APPLICATION_JSON).content(DETAILS))
                .andExpect(status().isOk());
        return id;
    }

    private String uploadImage(String caseId) throws Exception {
        String body = mockMvc.perform(multipart("/api/cases/" + caseId + "/images")
                        .file(new MockMultipartFile("file", "image.jpg", "image/jpeg", image()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(doctor)))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return body.replaceAll(".*\"imageId\":\"([0-9a-f-]{36})\".*", "$1");
    }

    private static GradingAnalyzeResponse graded(String supportingPng) {
        EcdReference reference = new EcdReference("completed", "A", "ecd_threshold_tree", 2400.0,
                new EcdBand(2232.0, 2497.0), Map.of("A", 1.0), 94, false, null);
        GradingExplanation explanation = new GradingExplanation("tree_shap", "A", 0.3, 0.7, List.of(), 0.05,
                new ImageAttributionMap("shap_weighted_layer4_map", supportingPng, null, 0.06, -0.01, 0.95), null);
        return new GradingAnalyzeResponse(null, null, "completed", null, "A", "hybrid", Map.of("A", 0.7), null,
                null, List.of(), reference, false, null, explanation);
    }

    private static CellularAnalyzeResponse cellular(String jpeg) {
        CellularBiomarkers bm = new CellularBiomarkers(1421, 2824.48, 354.04, 97.42, 27.52, 64.59, 1087,
                0.887, 0.035, 3.97, Map.of(), Map.of(), 1);
        return new CellularAnalyzeResponse(null, null, "completed", null,
                new ImageValidation("VALID_CORNEAL_IMAGE", true, 1296, 972, "JPEG"), "stardist", 0.796, true, bm,
                null, List.of(), true, null, null, null, new CellularImages(jpeg, jpeg, jpeg), 7.4);
    }

    private static byte[] image() throws Exception {
        return encode("jpeg");
    }

    private static byte[] png() throws Exception {
        return encode("png");
    }

    private static byte[] encode(String format) throws Exception {
        BufferedImage img = new BufferedImage(640, 480, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, format, out);
        return out.toByteArray();
    }
}
