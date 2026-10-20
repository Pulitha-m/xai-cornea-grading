package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.service.ImageService;
import com.cornealai.backend.audit.AuditService;
import com.cornealai.backend.cases.SlitLampFindings;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.dto.CaseDtos.CaseDetails;
import com.cornealai.backend.cases.dto.CaseDtos.CaseImage;
import com.cornealai.backend.cases.dto.CaseDtos.CaseResponse;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * The donor case workspace: open a case by tissue ID, enter its details once, and keep its images.
 * Any clinical user may work on any case. Module inputs are built here from the saved details, so
 * every module analyses the same values.
 */
@Service
public class CaseService {

    private final DonorCaseService donorCases;
    private final DonorCaseRepository cases;
    private final AnalysisImageRepository images;
    private final ImageService imageService;
    private final SignoffService signoffs;
    private final AuditService audit;
    private final ObjectMapper objectMapper;

    public CaseService(DonorCaseService donorCases, DonorCaseRepository cases, AnalysisImageRepository images,
                       ImageService imageService, SignoffService signoffs, AuditService audit,
                       ObjectMapper objectMapper) {
        this.signoffs = signoffs;
        this.audit = audit;
        this.donorCases = donorCases;
        this.cases = cases;
        this.images = images;
        this.imageService = imageService;
        this.objectMapper = objectMapper;
    }

    /** Opens the case for this tissue ID; {@code created} tells the controller whether it is new. */
    public Opened open(String tissueId, Long userId) {
        TissueNumber tissue = TissueNumber.parse(tissueId);
        boolean existed = donorCases.find(tissue).isPresent();
        DonorCase donorCase = donorCases.findOrCreate(tissue, userId);
        audit.record(userId, AuditService.CASE_VIEW, "case", donorCase.getId(), existed ? "opened" : "created");
        return new Opened(toResponse(donorCase), !existed);
    }

    public record Opened(CaseResponse body, boolean created) {
    }

    public CaseResponse findByTissueId(String tissueId, Long userId) {
        DonorCase donorCase = donorCases.find(TissueNumber.parse(tissueId))
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "tissueId",
                        "No case has this tissue ID yet."));
        audit.record(userId, AuditService.CASE_VIEW, "case", donorCase.getId(), "found by tissue ID");
        return toResponse(donorCase);
    }

    public CaseResponse get(UUID caseId, Long userId) {
        CaseResponse response = toResponse(donorCases.require(caseId));
        audit.record(userId, AuditService.CASE_VIEW, "case", caseId, null);
        return response;
    }

    public List<CaseResponse> recent(Long userId) {
        List<CaseResponse> found = cases.findTop20ByOrderByUpdatedAtDesc().stream().map(this::toResponse).toList();
        audit.record(userId, AuditService.CASE_LIST, null, null, found.size() + " cases");
        return found;
    }

    /** Replaces the case details (absent = not recorded). Validated before anything is changed. */
    public CaseResponse updateDetails(UUID caseId, CaseDetails details, Long userId) {
        String slitLampJson = objectMapper.writeValueAsString(SlitLampFindings.normalise(details.slitLamp()));
        DonorCase donorCase = donorCases.require(caseId);
        donorCase.setDonorAgeYears(details.donorAgeYears());
        donorCase.setDeathToPreservationHours(details.deathToPreservationHours());
        donorCase.setPreservationDate(details.preservationDate());
        donorCase.setEcd(details.ecd());
        donorCase.setCv(details.cv());
        donorCase.setHexPercent(details.hexPercent());
        donorCase.setSd(details.sd());
        donorCase.setTotalCellCount(details.totalCellCount());
        donorCase.setTotalAreaUm2(details.totalAreaUm2());
        donorCase.setSlitLampJson(slitLampJson);
        CaseResponse response = toResponse(cases.saveAndFlush(donorCase));
        audit.record(userId, AuditService.CASE_UPDATE, "case", caseId, "details");
        return response;
    }

    public ImageUploadResponse uploadImage(UUID caseId, byte[] data, Long userId) {
        return imageService.uploadToCase(donorCases.require(caseId), data, userId);
    }

    public List<CaseImage> images(UUID caseId) {
        donorCases.require(caseId);
        return images.findByDonorCaseIdOrderByCreatedAtDesc(caseId).stream()
                .map(i -> new CaseImage(i.getId(), i.getContentType(), i.getSizeBytes(), i.getWidth(), i.getHeight(),
                        i.getUploadedBy(), i.getCreatedAt()))
                .toList();
    }

    /** One of the case's images; 404 also when it belongs to another case. */
    public AnalysisImage requireImage(UUID caseId, UUID imageId) {
        AnalysisImage image = imageService.requireImage(imageId);
        if (!caseId.equals(image.getDonorCaseId())) {
            throw new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                    "The image was not found in this case.");
        }
        return image;
    }

    /** The decrypted, verified image bytes for viewing. */
    public byte[] imageContent(AnalysisImage image, Long userId) {
        byte[] data = imageService.readVerified(image);
        audit.record(userId, AuditService.IMAGE_VIEW, "image", image.getId(), null);
        return data;
    }

    /** The 24 grading features, in model order, from the case details (null = not recorded). */
    public Map<String, Object> gradingFeatures(DonorCase c) {
        Map<String, Object> features = new LinkedHashMap<>();
        features.put("ECD_CD_cells_per_mm2", c.getEcd());
        features.put("CV", c.getCv());
        features.put("HEX_percent", c.getHexPercent());
        features.put("SD", c.getSd());
        features.put("Total_Cell_Count", c.getTotalCellCount());
        features.put("Total_Area_um2", c.getTotalAreaUm2());
        features.putAll(slitLamp(c));
        return features;
    }

    /** The five disease-model measurements from the case details (null = not recorded, never 0). */
    public Map<String, Object> diseaseMeasurements(DonorCase c) {
        Map<String, Object> measurements = new LinkedHashMap<>();
        measurements.put("ECD_CD_cells_per_mm2", c.getEcd());
        measurements.put("SD", c.getSd());
        measurements.put("CV", c.getCv());
        measurements.put("HEX_percent", c.getHexPercent());
        measurements.put("Donor_Age", c.getDonorAgeYears());
        return measurements;
    }

    CaseResponse toResponse(DonorCase c) {
        CaseDetails details = new CaseDetails(c.getDonorAgeYears(), c.getDeathToPreservationHours(),
                c.getPreservationDate(), c.getEcd(), c.getCv(), c.getHexPercent(), c.getSd(), c.getTotalCellCount(),
                c.getTotalAreaUm2(), slitLamp(c));
        return new CaseResponse(c.getId(), donorCases.tissueNumberOf(c).value(), details,
                images.countByDonorCaseId(c.getId()), signoffs.latest(c.getId()).orElse(null), c.getCreatedAt(),
                c.getUpdatedAt());
    }

    private Map<String, Object> slitLamp(DonorCase c) {
        if (c.getSlitLampJson() == null) {
            return SlitLampFindings.normalise(Map.of());
        }
        return objectMapper.readValue(c.getSlitLampJson(), new TypeReference<LinkedHashMap<String, Object>>() {
        });
    }
}
