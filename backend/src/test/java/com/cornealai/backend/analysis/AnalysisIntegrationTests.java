package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.GradingResult;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.AnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.repository.AnalysisRunRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
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
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.ResultActions;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.List;
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

class AnalysisIntegrationTests extends IntegrationTestSupport {

    @MockitoBean
    private ImageStorage storage;

    @MockitoBean
    private MlServiceClient mlServiceClient;

    @Autowired
    private AnalysisImageRepository images;

    @Autowired
    private AnalysisRunRepository runs;

    @Autowired
    private com.cornealai.backend.cases.service.DonorCaseService donorCases;

    private AppUser doctor;
    private byte[] stored;

    @BeforeEach
    void setUp() {
        doctor = createUser("dr.upload", RoleName.DOCTOR);
        when(storage.bucket()).thenReturn("specular-images");
        // Remember what was stored so reads return the same bytes.
        doAnswer(invocation -> {
            stored = invocation.getArgument(1);
            return null;
        }).when(storage).store(anyString(), any(), anyString());
        when(storage.read(anyString())).thenAnswer(invocation -> stored);
    }

    // ---------------------------------------------------------------- upload

    @Test
    void validJpegIsStoredEncryptedUnderAServerGeneratedPath() throws Exception {
        byte[] jpeg = image("jpg", 640, 480);
        upload(doctor, " 12656r ", jpeg, "anything.exe")
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.caseId").value("12656R"))
                .andExpect(jsonPath("$.contentType").value("image/jpeg"))
                .andExpect(jsonPath("$.width").value(640))
                .andExpect(jsonPath("$.objectPath").doesNotExist());

        ArgumentCaptor<String> path = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<byte[]> bytes = ArgumentCaptor.forClass(byte[].class);
        verify(storage).store(path.capture(), bytes.capture(), eq("application/octet-stream"));
        // The path is only a new UUID: neither the case id nor the image format can be read from it.
        assertThat(path.getValue()).matches("images/[0-9a-f-]{36}").doesNotContain("12656");
        // Stored bytes are ciphertext, not the JPEG.
        assertThat(bytes.getValue()).isNotEqualTo(jpeg);
        assertThat(java.util.Arrays.copyOf(bytes.getValue(), 2)).isNotEqualTo(new byte[]{(byte) 0xFF, (byte) 0xD8});
        AnalysisImage saved = images.findAll().getFirst();
        assertThat(saved.getUploadedBy()).isEqualTo(doctor.getId());
        assertThat(saved.getObjectPath()).isEqualTo(path.getValue());
        assertThat(saved.isEncrypted()).isTrue();
        assertThat(saved.getSha256()).isNull();
        // The record refers to the donor case by its UUID; the tissue ID is not stored in plain text.
        assertThat(saved.getDonorCaseId()).isNotNull();
        assertThat(saved.getCaseId()).isEqualTo(saved.getDonorCaseId().toString());
    }

    @Test
    void unsupportedOrMisnamedFileIsRejectedBeforeStorage() throws Exception {
        upload(doctor, "12656R", image("bmp", 640, 480), "photo.png")
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_IMAGE_FORMAT"));
        upload(doctor, "12656R", "not an image".getBytes(), "scan.jpg")
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_IMAGE_FORMAT"));
        verify(storage, never()).store(anyString(), any(), anyString());
    }

    @Test
    void emptyTruncatedAndTooSmallImagesAreRejected() throws Exception {
        upload(doctor, "12656R", new byte[0], "empty.jpg")
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("IMAGE_DECODE_FAILED"));
        byte[] png = image("png", 640, 480);
        upload(doctor, "12656R", java.util.Arrays.copyOf(png, 12), "cut.png")
                .andExpect(jsonPath("$.code").value("IMAGE_DECODE_FAILED"));
        upload(doctor, "12656R", image("png", 100, 100), "small.png")
                .andExpect(jsonPath("$.code").value("IMAGE_DIMENSIONS_INVALID"));
        verify(storage, never()).store(anyString(), any(), anyString());
    }

    @Test
    void storageFailureIsReportedWithoutLeakingDetails() throws Exception {
        doThrow(new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null,
                "The image could not be stored or retrieved. Try again later."))
                .when(storage).store(anyString(), any(), anyString());

        upload(doctor, "12656R", image("jpg", 640, 480), "a.jpg")
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("IMAGE_STORAGE_ACCESS_FAILED"));
        assertThat(images.count()).isZero();
    }

    @Test
    void nonClinicalRoleCannotUpload() throws Exception {
        AppUser support = createUser("support.upload", RoleName.SUPPORT_STAFF);
        upload(support, "12656R", image("jpg", 640, 480), "a.jpg").andExpect(status().isForbidden());
        verify(storage, never()).store(anyString(), any(), anyString());
    }

    // ---------------------------------------------------------------- analysis

    @Test
    void analysisSendsStoredBytesAndRecordsTheRun() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyze(anyString(), anyString(), any(), anyString())).thenReturn(response("completed"));

        analyze(doctor, "12656R", imageId, 2400.0)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analysisId").isNotEmpty())
                .andExpect(jsonPath("$.grading.grade").value("A"));

        ArgumentCaptor<String> features = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<byte[]> bytes = ArgumentCaptor.forClass(byte[].class);
        verify(mlServiceClient).analyze(anyString(), features.capture(), bytes.capture(), anyString());
        assertThat(bytes.getValue()).isEqualTo(image("jpg", 640, 480));  // decrypted, as uploaded
        assertThat(features.getValue()).contains("\"ECD_CD_cells_per_mm2\":2400.0").contains("\"Stroma_Has_Scar\":null");

        List<AnalysisRun> recorded = runs.findByImageId(imageId);
        assertThat(recorded).singleElement().satisfies(run -> {
            assertThat(run.getStatus()).isEqualTo("completed");
            // Linked to the donor case by UUID; the tissue ID is not stored in the run.
            assertThat(run.getDonorCaseId()).isNotNull();
            assertThat(run.getCaseId()).isEqualTo(run.getDonorCaseId().toString());
            assertThat(run.getResultJson()).doesNotContain("12656R");
            assertThat(run.getRequestedBy()).isEqualTo(doctor.getId());
            assertThat(run.getResultJson()).contains("\"grade\":\"A\"");
            assertThat(run.getEcd()).isEqualTo(2400.0);
            assertThat(run.getClinicalFeaturesJson()).contains("ECD_CD_cells_per_mm2");
        });
    }

    @Test
    void anotherClinicianCanAnalyseTheCase() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        AppUser otherDoctor = createUser("dr.other", RoleName.DOCTOR);

        when(mlServiceClient.analyze(anyString(), anyString(), any(), anyString())).thenReturn(response("completed"));

        // Any DOCTOR or NURSE may work on any case, not only the uploader.
        analyze(otherDoctor, "12656R", imageId, 2400.0).andExpect(status().isOk());
        assertThat(runs.findByImageId(imageId)).singleElement()
                .satisfies(run -> assertThat(run.getRequestedBy()).isEqualTo(otherDoctor.getId()));
    }

    @Test
    void imageCannotBeAnalysedUnderADifferentCase() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        analyze(doctor, "12657L", imageId, null)
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("TISSUE_ACCESS_DENIED"));
        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void unknownImageIsNotFound() throws Exception {
        analyze(doctor, "12656R", UUID.randomUUID(), null)
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("IMAGE_NOT_FOUND"));
    }

    @Test
    void tamperedStoredImageIsNotAnalysed() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        stored = image("jpg", 641, 480);  // different bytes than were uploaded

        analyze(doctor, "12656R", imageId, null)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("IMAGE_STORAGE_ACCESS_FAILED"));
        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void changedCiphertextIsNotAnalysed() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        stored[stored.length - 20] ^= 0x01;

        analyze(doctor, "12656R", imageId, null)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("IMAGE_STORAGE_ACCESS_FAILED"));
        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void anotherImagesObjectIsNotAcceptedInItsPlace() throws Exception {
        uploadedImage(doctor, "12656R");
        byte[] firstObject = stored;
        UUID secondId = uploadedImage(doctor, "12656R");
        stored = firstObject;  // valid ciphertext, but encrypted for the other image id

        analyze(doctor, "12656R", secondId, null)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("IMAGE_STORAGE_ACCESS_FAILED"));
        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void imageStoredBeforeEncryptionIsStillVerifiedAndAnalysed() throws Exception {
        byte[] jpeg = image("jpg", 640, 480);
        var donorCase = donorCases.findOrCreate(com.cornealai.backend.cases.TissueNumber.parse("12656R"), doctor.getId());
        AnalysisImage legacy = new AnalysisImage();
        legacy.setId(UUID.randomUUID());
        legacy.setCaseId(donorCase.getId().toString());
        legacy.setDonorCaseId(donorCase.getId());
        legacy.setBucket("specular-images");
        legacy.setObjectPath("legacy/" + legacy.getId() + ".jpg");
        legacy.setContentType("image/jpeg");
        legacy.setSizeBytes(jpeg.length);
        legacy.setSha256(java.util.HexFormat.of().formatHex(
                java.security.MessageDigest.getInstance("SHA-256").digest(jpeg)));
        legacy.setEncrypted(false);
        legacy.setWidth(640);
        legacy.setHeight(480);
        legacy.setUploadedBy(doctor.getId());
        images.saveAndFlush(legacy);
        stored = jpeg;
        when(mlServiceClient.analyze(anyString(), anyString(), any(), anyString())).thenReturn(response("completed"));

        analyze(doctor, "12656R", legacy.getId(), null).andExpect(status().isOk());

        stored = image("jpg", 641, 480);
        analyze(doctor, "12656R", legacy.getId(), null)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("IMAGE_STORAGE_ACCESS_FAILED"));
    }

    @Test
    void imageRejectedByMlServiceIsReportedAndRecorded() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyze(any(), any(), any(), any())).thenThrow(new AnalysisRejectedException(
                HttpStatus.UNPROCESSABLE_CONTENT, "INVALID_IMAGE_DOMAIN", "image",
                "Upload a specular microscopy image showing corneal endothelial cells."));

        analyze(doctor, "12656R", imageId, 2400.0)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("INVALID_IMAGE_DOMAIN"))
                .andExpect(jsonPath("$.fieldErrors.image").exists())
                .andExpect(jsonPath("$.grading").doesNotExist());

        assertThat(runs.findByImageId(imageId)).singleElement().satisfies(run -> {
            assertThat(run.getStatus()).isEqualTo("rejected");
            assertThat(run.getErrorCode()).isEqualTo("INVALID_IMAGE_DOMAIN");
            assertThat(run.getResultJson()).isNull();
        });
    }

    @Test
    void malformedMlResponseIsAFailureNotAResult() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyze(any(), any(), any(), any())).thenReturn(null);

        analyze(doctor, "12656R", imageId, 2400.0)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("MODEL_INFERENCE_FAILED"));
        assertThat(runs.findByImageId(imageId)).singleElement()
                .satisfies(run -> assertThat(run.getStatus()).isEqualTo("rejected"));
    }

    @Test
    void requestWithoutClinicalFeaturesIsRejectedBeforeCallingMlService() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        mockMvc.perform(post("/api/analysis")
                        .header(HttpHeaders.AUTHORIZATION, bearer(doctor))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"caseId\":\"CASE-1\",\"imageId\":\"%s\"}".formatted(imageId)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.clinicalFeatures").exists());
        verify(mlServiceClient, never()).analyze(any(), any(), any(), any());
    }

    @Test
    void featureValidationErrorsFromMlServiceAreReportedPerField() throws Exception {
        UUID imageId = uploadedImage(doctor, "12656R");
        when(mlServiceClient.analyze(any(), any(), any(), any())).thenThrow(new AnalysisRejectedException(
                HttpStatus.UNPROCESSABLE_CONTENT, "MISSING_CLINICAL_FEATURES", "HEX_percent",
                "HEX_percent is required (use null if not recorded).",
                java.util.Map.of("HEX_percent", "HEX_percent is required (use null if not recorded).",
                        "CV", "CV must be a number (%).")));

        analyze(doctor, "12656R", imageId, 2400.0)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.code").value("MISSING_CLINICAL_FEATURES"))
                .andExpect(jsonPath("$.fieldErrors.HEX_percent").exists())
                .andExpect(jsonPath("$.fieldErrors.CV").exists());
    }

    // ---------------------------------------------------------------- helpers

    private UUID uploadedImage(AppUser user, String caseId) throws Exception {
        String body = upload(user, caseId, image("jpg", 640, 480), "image.jpg")
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return UUID.fromString(body.replaceAll(".*\"imageId\":\"([0-9a-f-]{36})\".*", "$1"));
    }

    private ResultActions upload(AppUser user, String caseId, byte[] data, String filename) throws Exception {
        return mockMvc.perform(multipart("/api/analysis/images")
                .file(new MockMultipartFile("file", filename, "image/png", data))
                .param("caseId", caseId)
                .header(HttpHeaders.AUTHORIZATION, bearer(user)));
    }

    private ResultActions analyze(AppUser user, String caseId, UUID imageId, Double ecd) throws Exception {
        String ecdJson = ecd == null ? "null" : ecd.toString();
        String features = "{\"ECD_CD_cells_per_mm2\":%s,\"Stroma_Has_Scar\":null}".formatted(ecdJson);
        return mockMvc.perform(post("/api/analysis")
                .header(HttpHeaders.AUTHORIZATION, bearer(user))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"caseId\":\"%s\",\"imageId\":\"%s\",\"clinicalFeatures\":%s}".formatted(caseId, imageId, features)));
    }

    private static AnalyzeResponse response(String status) {
        GradingResult grading = new GradingResult("completed", null, "A", "hybrid_random_forest_24_resnet50",
                java.util.Map.of("A", 0.6, "A+", 0.3, "B", 0.1), java.util.List.of(), java.util.List.of(), null,
                false, "Grade from the 24-feature model.");
        return new AnalyzeResponse(null, "12656R", status, null, null, grading, null, null);
    }

    private static byte[] image(String format, int width, int height) throws Exception {
        BufferedImage img = new BufferedImage(width, height, BufferedImage.TYPE_BYTE_GRAY);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(img, format.equals("jpg") ? "jpeg" : format, out);
        return out.toByteArray();
    }
}
