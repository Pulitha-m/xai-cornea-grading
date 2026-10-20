package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.common.crypto.BlindIndex;
import com.cornealai.backend.common.crypto.FieldCipher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

/**
 * Donor cases by tissue ID. The tissue ID is stored only encrypted and found by its blind index;
 * everything else (images, runs, the ML service) refers to the case by its random UUID.
 */
@Service
public class DonorCaseService {

    private final DonorCaseRepository cases;
    private final FieldCipher cipher;
    private final BlindIndex blindIndex;

    public DonorCaseService(DonorCaseRepository cases, FieldCipher cipher, BlindIndex blindIndex) {
        this.cases = cases;
        this.cipher = cipher;
        this.blindIndex = blindIndex;
    }

    /** The case with this id, or 404. */
    public DonorCase require(UUID id) {
        return cases.findById(id).orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND,
                "CASE_NOT_FOUND", "caseId", "The case was not found."));
    }

    public Optional<DonorCase> find(TissueNumber tissue) {
        return cases.findByTissueNumberBidx(index(tissue));
    }

    /** The case for this tissue ID, created on first use. */
    public DonorCase findOrCreate(TissueNumber tissue, Long userId) {
        String index = index(tissue);
        return cases.findByTissueNumberBidx(index).orElseGet(() -> create(tissue, index, userId));
    }

    /**
     * The case the request names, provided the image belongs to it. An unknown tissue ID gets the same
     * answer as a mismatch, so the response does not reveal which tissue IDs exist.
     */
    public DonorCase requireCaseOf(AnalysisImage image, TissueNumber tissue) {
        return find(tissue)
                .filter(found -> found.getId().equals(image.getDonorCaseId()))
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED",
                        "caseId", "The image belongs to a different case."));
    }

    /** Decrypts the tissue ID; only for a caller already authorised to see this case. */
    public TissueNumber tissueNumberOf(DonorCase donorCase) {
        return new TissueNumber(cipher.decrypt(donorCase.getTissueNumberEnc(), DonorCase.TISSUE_NUMBER,
                donorCase.getId()));
    }

    private DonorCase create(TissueNumber tissue, String index, Long userId) {
        DonorCase donorCase = new DonorCase();
        donorCase.setId(UUID.randomUUID());
        donorCase.setTissueNumberEnc(cipher.encrypt(tissue.value(), DonorCase.TISSUE_NUMBER, donorCase.getId()));
        donorCase.setTissueNumberBidx(index);
        donorCase.setCreatedBy(userId);
        try {
            return cases.saveAndFlush(donorCase);
        } catch (DataIntegrityViolationException e) {
            // Created concurrently by another request: the unique blind index decides, use that case.
            return cases.findByTissueNumberBidx(index).orElseThrow(() -> e);
        }
    }

    private String index(TissueNumber tissue) {
        return blindIndex.of(DonorCase.TISSUE_NUMBER_INDEX, tissue.value());
    }
}
