package com.cornealai.backend.security;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.GradingResult;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RoleBasedAccessIntegrationTests extends IntegrationTestSupport {

    private static final byte[] IMAGE_BYTES = {1, 2, 3, 4};

    /** For requests refused before the image is looked up; the id does not exist. */
    private static final String ANALYZE_BODY = """
            {"caseId":"CASE-1","imageId":"%s","clinicalFeatures":{}}
            """.formatted(UUID.randomUUID());

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @MockitoBean
    private ImageStorage imageStorage;

    @Autowired
    private AnalysisImageRepository imageRepository;

    @BeforeEach
    void stubMlService() {
        when(mlServiceClient.analyze(any(), any(), any(), any()))
                .thenReturn(new AnalyzeResponse(null, "CASE-1", "partial", null, null,
                        new GradingResult("completed", null, "A", "hybrid_random_forest_24_resnet50", null, null, null,
                                null, false, "Grade from the 24-feature model."),
                        null, null));
        when(imageStorage.read(any())).thenReturn(IMAGE_BYTES);
    }

    /** Stores an image record owned by {@code owner} and returns an analysis body referencing it. */
    private String analyzeBodyFor(AppUser owner) throws Exception {
        AnalysisImage image = new AnalysisImage();
        image.setId(UUID.randomUUID());
        image.setCaseId("CASE-1");
        image.setBucket("test-bucket");
        image.setObjectPath("CASE-1/" + image.getId() + ".jpg");
        image.setContentType("image/jpeg");
        image.setSizeBytes(IMAGE_BYTES.length);
        image.setSha256(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(IMAGE_BYTES)));
        image.setWidth(1296);
        image.setHeight(972);
        image.setUploadedBy(owner.getId());
        imageRepository.saveAndFlush(image);
        return """
                {"caseId":"CASE-1","imageId":"%s","clinicalFeatures":{}}
                """.formatted(image.getId());
    }

    // ---------- Administrative endpoints ----------

    @Test
    void adminCanListAndCreateUsers() throws Exception {
        AppUser admin = createUser("admin.one", RoleName.ADMIN);

        mockMvc.perform(get("/api/users").header(HttpHeaders.AUTHORIZATION, bearer(admin)))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/users")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"New.Nurse","email":"New.Nurse@CornealAI.test","fullName":"New Nurse",
                                 "role":"NURSE","password":"A-strong-password-1"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.username").value("new.nurse"))
                .andExpect(jsonPath("$.email").value("new.nurse@cornealai.test"))
                .andExpect(jsonPath("$.role").value("NURSE"))
                .andExpect(jsonPath("$.passwordHash").doesNotExist());

        AppUser created = userRepository.findByUsernameOrEmail("new.nurse").orElseThrow();
        assertThat(created.getPasswordHash()).startsWith("$2").isNotEqualTo("A-strong-password-1");
    }

    @Test
    void nurseCannotAccessAdminEndpoints() throws Exception {
        AppUser nurse = createUser("nurse.one", RoleName.NURSE);

        mockMvc.perform(get("/api/users").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403));

        mockMvc.perform(post("/api/users")
                        .header(HttpHeaders.AUTHORIZATION, bearer(nurse))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(newUserJson("someone", "DOCTOR")))
                .andExpect(status().isForbidden());
    }

    @Test
    void managerCanViewStaffDirectoryButNotManageUsers() throws Exception {
        AppUser manager = createUser("manager.one", RoleName.MANAGER);
        AppUser doctor = createUser("dr.target", RoleName.DOCTOR);

        mockMvc.perform(get("/api/users").header(HttpHeaders.AUTHORIZATION, bearer(manager)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.username == 'dr.target')]").exists());

        mockMvc.perform(post("/api/users")
                        .header(HttpHeaders.AUTHORIZATION, bearer(manager))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(newUserJson("manager.made", "ADMIN")))
                .andExpect(status().isForbidden());

        mockMvc.perform(patch("/api/users/" + doctor.getId() + "/status")
                        .header(HttpHeaders.AUTHORIZATION, bearer(manager))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":false}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestToAdminEndpointReturns401() throws Exception {
        mockMvc.perform(get("/api/users"))
                .andExpect(status().isUnauthorized());
    }

    // ---------- Role assignment ----------

    @ParameterizedTest
    @EnumSource(value = RoleName.class, names = {"MANAGER", "DOCTOR", "NURSE", "SUPPORT_STAFF"})
    void nonAdminsCannotAssignRoles(RoleName actorRole) throws Exception {
        AppUser actor = createUser("actor." + actorRole.name().toLowerCase(), actorRole);

        // Neither to themselves...
        mockMvc.perform(put("/api/users/" + actor.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(actor))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"ADMIN\"}"))
                .andExpect(status().isForbidden());

        // ...nor to anyone else.
        AppUser other = createUser("other." + actorRole.name().toLowerCase(), RoleName.SUPPORT_STAFF);
        mockMvc.perform(put("/api/users/" + other.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(actor))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"ADMIN\"}"))
                .andExpect(status().isForbidden());

        assertThat(userRepository.findById(actor.getId()).orElseThrow().getRole().getName()).isEqualTo(actorRole);
        assertThat(userRepository.findById(other.getId()).orElseThrow().getRole().getName()).isEqualTo(RoleName.SUPPORT_STAFF);
    }

    @Test
    void adminCanAssignRolesAndNewAuthoritiesApplyImmediately() throws Exception {
        AppUser admin = createUser("admin.assigner", RoleName.ADMIN);
        AppUser support = createUser("support.promoted", RoleName.SUPPORT_STAFF);
        String supportToken = bearer(support);

        mockMvc.perform(post("/api/analysis").header(HttpHeaders.AUTHORIZATION, supportToken)
                        .contentType(MediaType.APPLICATION_JSON).content(ANALYZE_BODY))
                .andExpect(status().isForbidden());

        mockMvc.perform(put("/api/users/" + support.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"NURSE\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("NURSE"));

        // Same, unchanged access token: authorities are re-read from the database.
        mockMvc.perform(post("/api/analysis").header(HttpHeaders.AUTHORIZATION, supportToken)
                        .contentType(MediaType.APPLICATION_JSON).content(analyzeBodyFor(support)))
                .andExpect(status().isOk());
    }

    @Test
    void adminCannotChangeOwnRoleOrDisableSelf() throws Exception {
        AppUser admin = createUser("admin.self", RoleName.ADMIN);

        mockMvc.perform(put("/api/users/" + admin.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"NURSE\"}"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(patch("/api/users/" + admin.getId() + "/status")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":false}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidRoleNameIsRejected() throws Exception {
        AppUser admin = createUser("admin.invalid", RoleName.ADMIN);
        AppUser doctor = createUser("dr.invalid", RoleName.DOCTOR);

        mockMvc.perform(put("/api/users/" + doctor.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"SUPERUSER\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createUserValidatesInput() throws Exception {
        AppUser admin = createUser("admin.validate", RoleName.ADMIN);

        mockMvc.perform(post("/api/users")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"x","email":"not-an-email","fullName":"","role":"NURSE","password":"short"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.username").exists())
                .andExpect(jsonPath("$.fieldErrors.email").exists())
                .andExpect(jsonPath("$.fieldErrors.fullName").exists())
                .andExpect(jsonPath("$.fieldErrors.password").exists());
    }

    @Test
    void duplicateUserIsRejected() throws Exception {
        AppUser admin = createUser("admin.dupe", RoleName.ADMIN);
        createUser("dr.dupe", RoleName.DOCTOR);

        mockMvc.perform(post("/api/users")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(newUserJson("DR.DUPE", "DOCTOR")))
                .andExpect(status().isConflict());
    }

    // ---------- Clinical analysis ----------

    @Test
    void doctorCanRunAnalysis() throws Exception {
        AppUser doctor = createUser("dr.analysis", RoleName.DOCTOR);

        mockMvc.perform(post("/api/analysis").header(HttpHeaders.AUTHORIZATION, bearer(doctor))
                        .contentType(MediaType.APPLICATION_JSON).content(analyzeBodyFor(doctor)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("CASE-1"));
    }

    @Test
    void nurseCanRunAnalysis() throws Exception {
        AppUser nurse = createUser("nurse.analysis", RoleName.NURSE);

        mockMvc.perform(post("/api/analysis").header(HttpHeaders.AUTHORIZATION, bearer(nurse))
                        .contentType(MediaType.APPLICATION_JSON).content(analyzeBodyFor(nurse)))
                .andExpect(status().isOk());
    }

    @ParameterizedTest
    @EnumSource(value = RoleName.class, names = {"SUPPORT_STAFF", "MANAGER", "ADMIN"})
    void nonClinicalRolesCannotAccessClinicalAnalysis(RoleName role) throws Exception {
        AppUser user = createUser("nonclinical." + role.name().toLowerCase(), role);

        mockMvc.perform(post("/api/analysis").header(HttpHeaders.AUTHORIZATION, bearer(user))
                        .contentType(MediaType.APPLICATION_JSON).content(ANALYZE_BODY))
                .andExpect(status().isForbidden());

        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void unauthenticatedAnalysisRequestReturns401() throws Exception {
        mockMvc.perform(post("/api/analysis")
                        .contentType(MediaType.APPLICATION_JSON).content(ANALYZE_BODY))
                .andExpect(status().isUnauthorized());

        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void healthEndpointIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    private static String newUserJson(String username, String role) {
        return """
                {"username":"%s","email":"%s@cornealai.test","fullName":"Someone",
                 "role":"%s","password":"A-strong-password-1"}
                """.formatted(username, username, role);
    }
}
