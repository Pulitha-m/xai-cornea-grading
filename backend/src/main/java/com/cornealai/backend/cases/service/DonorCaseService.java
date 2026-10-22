package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.common.crypto.BlindIndex;
import com.cornealai.backend.common.crypto.FieldCipher;
import jakarta.persistence.EntityManager;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Donor cases by tissue ID. The tissue ID is stored only encrypted and found by its blind index;
 * everything else (images, runs, the ML service) refers to the case by its random UUID.
 */
@Service
public class DonorCaseService {

    /** Blind indexes per IN query (well under PostgreSQL's bind-parameter limit). */
    private static final int LOOKUP_CHUNK = 500;

    private final DonorCaseRepository cases;
    private final FieldCipher cipher;
    private final BlindIndex blindIndex;
    private final EntityManager entityManager;

    public DonorCaseService(DonorCaseRepository cases, FieldCipher cipher, BlindIndex blindIndex,
                            EntityManager entityManager) {
        this.cases = cases;
        this.cipher = cipher;
        this.blindIndex = blindIndex;
        this.entityManager = entityManager;
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

    /**
     * The existing cases for these tissue IDs, found with one query (bulk import). Tissue IDs without a
     * case are absent from the map.
     */
    public Map<TissueNumber, DonorCase> findAll(Collection<TissueNumber> tissues) {
        Map<String, TissueNumber> byIndex = new HashMap<>();
        tissues.forEach(t -> byIndex.put(index(t), t));
        Map<TissueNumber, DonorCase> found = new HashMap<>();
        List<String> indexes = List.copyOf(byIndex.keySet());
        for (int from = 0; from < indexes.size(); from += LOOKUP_CHUNK) {
            cases.findByTissueNumberBidxIn(indexes.subList(from, Math.min(from + LOOKUP_CHUNK, indexes.size())))
                    .forEach(c -> found.put(byIndex.get(c.getTissueNumberBidx()), c));
        }
        return found;
    }

    /**
     * A new, not yet saved case for this tissue ID. Pass it to {@link #persist} once its details are set,
     * inside the caller's transaction.
     */
    public DonorCase newCase(TissueNumber tissue, Long userId) {
        return build(tissue, index(tissue), userId);
    }

    /**
     * Schedules the insert of a case from {@link #newCase} without a lookup or flush (the id is new), so
     * a bulk import writes all its cases in batches at the end. A tissue ID created meanwhile by another
     * request fails at {@link #flush} with a {@link DataIntegrityViolationException}.
     */
    public void persist(DonorCase donorCase) {
        entityManager.persist(donorCase);
    }

    /** Writes pending changes now; constraint violations surface here as Spring exceptions. */
    public void flush() {
        cases.flush();
    }

    private DonorCase build(TissueNumber tissue, String index, Long userId) {
        DonorCase donorCase = new DonorCase();
        donorCase.setId(UUID.randomUUID());
        donorCase.setTissueNumberEnc(cipher.encrypt(tissue.value(), DonorCase.TISSUE_NUMBER, donorCase.getId()));
        donorCase.setTissueNumberBidx(index);
        donorCase.setCreatedBy(userId);
        return donorCase;
    }

    private DonorCase create(TissueNumber tissue, String index, Long userId) {
        DonorCase donorCase = build(tissue, index, userId);
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
