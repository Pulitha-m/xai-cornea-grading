package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeRequest;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.DiseaseAnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.analysis.repository.DiseaseAnalysisRunRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Runs the v2 disease detection + severity model on a stored image, with the same access
 * policy as {@link AnalysisService}: only the uploader may analyse an image, its bytes are read
 * server-side and verified (decrypted, see ImageService). Every attempt is recorded.
 */
@Service
public class DiseaseAnalysisService {

    private final AnalysisImageRepository images;
    private final DiseaseAnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public DiseaseAnalysisService(
            AnalysisImageRepository images,
            DiseaseAnalysisRunRepository runs,
            ImageService imageService,
            DonorCaseService donorCases,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper
    ) {
        this.images = images;
        this.runs = runs;
        this.imageService = imageService;
        this.donorCases = donorCases;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
    }

    public DiseaseAnalyzeResponse analyze(DiseaseAnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = images.findById(request.imageId())
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                        "The image was not found. Upload it again."));

        if (!image.getUploadedBy().equals(userId)) {
            throw new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED", "imageId",
                    "You do not have access to this image.");
        }
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        String caseId = donorCase.getId().toString();

        DiseaseAnalysisRun run = new DiseaseAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setDonorCaseId(donorCase.getId());
        run.setRequestedBy(userId);
        run.setForced(request.force());
        String measurementsJson = objectMapper.writeValueAsString(request.measurements());
        run.setMeasurementsJson(measurementsJson);

        try {
            byte[] data = imageService.readVerified(image);
            String filename = image.getId() + (image.getContentType().equals("image/png") ? ".png" : ".jpg");
            DiseaseAnalyzeResponse result = mlServiceClient.analyzeDisease(caseId, measurementsJson, request.force(),
                    data, filename);
            if (result == null || result.status() == null
                    || (!DiseaseAnalyzeResponse.INPUT_CHECK_FAILED.equals(result.status()) && result.diseases() == null)) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The analysis could not be completed. Try again later.");
            }
            DiseaseAnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);  // stored with the case UUID only

            run.setStatus(response.status());
            run.setResultJson(objectMapper.writeValueAsString(response.withoutGradcam()));
            runs.save(run);
            return response.withCaseId(tissue.value());
        } catch (AnalysisRejectedException e) {
            run.setStatus("rejected");
            run.setErrorCode(e.getCode());
            runs.save(run);
            throw e;
        }
    }
}
