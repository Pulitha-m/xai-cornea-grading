package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.audit.AuditService;
import com.cornealai.backend.cases.dto.CaseDtos.MatchCandidateView;
import com.cornealai.backend.cases.dto.CaseDtos.Serology;
import com.cornealai.backend.cases.dto.CaseDtos.Signoff;
import com.cornealai.backend.cases.dto.CaseDtos.SignoffRequest;
import com.cornealai.backend.cases.dto.CaseDtos.SignoffSummary;
import com.cornealai.backend.cases.entity.CaseSignoff;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.CaseAnalysisRepository;
import com.cornealai.backend.cases.repository.CaseSignoffRepository;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.common.crypto.FieldCipher;
import com.cornealai.backend.transplant.GraftRepository;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.repository.AppUserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Specialist sign-off, serology and recommendation candidates. Sign-offs are append-only; serology
 * results are encrypted and only doctors may read or record them. Every decryption is audited.
 */
@Service
public class SignoffService {

    private final DonorCaseService donorCases;
    private final DonorCaseRepository cases;
    private final CaseSignoffRepository signoffs;
    private final CaseAnalysisRepository analyses;
    private final AppUserRepository users;
    private final FieldCipher cipher;
    private final AuditService audit;
    private final GraftRepository grafts;
    private final ObjectMapper objectMapper;

    public SignoffService(DonorCaseService donorCases, DonorCaseRepository cases, CaseSignoffRepository signoffs,
                          CaseAnalysisRepository analyses, AppUserRepository users, FieldCipher cipher,
                          AuditService audit, GraftRepository grafts, ObjectMapper objectMapper) {
        this.grafts = grafts;
        this.donorCases = donorCases;
        this.cases = cases;
        this.signoffs = signoffs;
        this.analyses = analyses;
        this.users = users;
        this.cipher = cipher;
        this.audit = audit;
        this.objectMapper = objectMapper;
    }

    // ---------------------------------------------------------------- sign-off

    public Signoff signOff(UUID caseId, SignoffRequest request, Long userId) {
        donorCases.require(caseId);
        if (request.caseAnalysisId() != null && analyses.findById(request.caseAnalysisId())
                .filter(a -> caseId.equals(a.getDonorCaseId())).isEmpty()) {
            throw new AnalysisRejectedException(HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND", "caseAnalysisId",
                    "The analysis was not found in this case.");
        }
        CaseSignoff signoff = new CaseSignoff();
        signoff.setId(UUID.randomUUID());
        signoff.setDonorCaseId(caseId);
        signoff.setCaseAnalysisId(request.caseAnalysisId());
        signoff.setSignedBy(userId);
        signoff.setConfirmedGrade(request.confirmedGrade());
        signoff.setDiseaseFinding(request.diseaseFinding());
        signoff.setEcd(request.ecd());
        signoff.setCv(request.cv());
        signoff.setHexPercent(request.hexPercent());
        String notes = request.notes() == null || request.notes().isBlank() ? null : request.notes().strip();
        signoff.setNotesEnc(cipher.encrypt(notes, CaseSignoff.NOTES, signoff.getId()));
        signoffs.saveAndFlush(signoff);
        audit.record(userId, AuditService.SIGNOFF_CREATE, "case", caseId,
                "grade " + request.confirmedGrade() + ", finding " + request.diseaseFinding());
        return toSignoff(signoff, names(List.of(signoff)));
    }

    /** All sign-offs of the case, newest first, with their (decrypted) notes. */
    public List<Signoff> signoffs(UUID caseId, Long userId) {
        donorCases.require(caseId);
        List<CaseSignoff> found = signoffs.findByDonorCaseIdOrderByCreatedAtDesc(caseId);
        if (found.stream().anyMatch(s -> s.getNotesEnc() != null)) {
            audit.record(userId, AuditService.SIGNOFF_VIEW, "case", caseId, found.size() + " sign-offs");
        }
        Map<Long, String> names = names(found);
        return found.stream().map(s -> toSignoff(s, names)).toList();
    }

    /** The current sign-off of a case, for display with the case (no notes). */
    public Optional<SignoffSummary> latest(UUID caseId) {
        return signoffs.findFirstByDonorCaseIdOrderByCreatedAtDesc(caseId).map(s -> new SignoffSummary(
                s.getConfirmedGrade(), s.getDiseaseFinding(), names(List.of(s)).get(s.getSignedBy()), s.getCreatedAt()));
    }

    // ---------------------------------------------------------------- serology

    public Serology serology(UUID caseId, Long userId) {
        DonorCase donorCase = donorCases.require(caseId);
        audit.record(userId, AuditService.SEROLOGY_VIEW, "case", caseId, null);
        return readSerology(donorCase);
    }

    public Serology updateSerology(UUID caseId, Serology request, Long userId) {
        DonorCase donorCase = donorCases.require(caseId);
        Map<String, String> results = new java.util.LinkedHashMap<>();
        results.put("hiv", request.hiv());
        results.put("hbv", request.hbv());
        results.put("hcv", request.hcv());
        results.put("syphilis", request.syphilis());
        donorCase.setSerologyEnc(cipher.encrypt(objectMapper.writeValueAsString(results), DonorCase.SEROLOGY,
                donorCase.getId()));
        donorCase.setSerologyClear(serologyClear(results.values()));
        cases.saveAndFlush(donorCase);
        audit.record(userId, AuditService.SEROLOGY_UPDATE, "case", caseId, null);
        return readSerology(donorCase);
    }

    /** False when any result is positive; true only when all four are negative; otherwise unknown. */
    static Boolean serologyClear(java.util.Collection<String> results) {
        if (results.contains("Positive")) {
            return false;
        }
        return results.stream().allMatch("Negative"::equals) ? true : null;
    }

    private Serology readSerology(DonorCase donorCase) {
        String json = cipher.decrypt(donorCase.getSerologyEnc(), DonorCase.SEROLOGY, donorCase.getId());
        if (json == null) {
            return new Serology(null, null, null, null, donorCase.getSerologyClear());
        }
        Map<?, ?> results = objectMapper.readValue(json, Map.class);
        return new Serology((String) results.get("hiv"), (String) results.get("hbv"), (String) results.get("hcv"),
                (String) results.get("syphilis"), donorCase.getSerologyClear());
    }

    // ---------------------------------------------------------------- candidates

    /**
     * Days a cornea can be stored (Eusol-C), as in the recommendation module's matching dataset
     * (ml/recommendation/config.yaml, matching.storage_days). Older corneas are no longer in stock.
     */
    public static final int STORAGE_DAYS = 14;

    /** The candidates in stock, and how many signed-off corneas were left out (allocated or past storage). */
    public record CandidateSet(List<MatchCandidateView> inStock, int notInStock) {
    }

    /**
     * Signed-off corneas in stock as recommendation candidates, newest sign-off per case, in the
     * recommendation module's MatchCandidate fields (confirmed values only). Corneas already allocated to
     * a recipient, or stored longer than {@link #STORAGE_DAYS}, are left out.
     */
    public List<MatchCandidateView> candidates(Long userId) {
        return candidateSet(userId).inStock();
    }

    public CandidateSet candidateSet(Long userId) {
        Set<UUID> seen = new HashSet<>();
        List<MatchCandidateView> out = new ArrayList<>();
        int notInStock = 0;
        for (CaseSignoff s : signoffs.findAllByOrderByCreatedAtDesc()) {
            if (!seen.add(s.getDonorCaseId())) {
                continue;
            }
            DonorCase c = donorCases.require(s.getDonorCaseId());
            Double days = c.getPreservationDate() == null ? null
                    : (double) ChronoUnit.DAYS.between(c.getPreservationDate(), LocalDate.now());
            if (grafts.existsByDonorCaseId(c.getId()) || (days != null && days > STORAGE_DAYS)) {
                notInStock++;
                continue;
            }
            String serology = c.getSerologyClear() == null ? "Unknown" : c.getSerologyClear() ? "Yes" : "No";
            out.add(new MatchCandidateView(c.getId().toString(), donorCases.tissueNumberOf(c).value(),
                    s.getConfirmedGrade(), s.getEcd(), s.getCv(), s.getHexPercent(),
                    c.getDonorAgeYears() == null ? null : c.getDonorAgeYears().doubleValue(),
                    c.getDeathToPreservationHours(), days, serology, s.getDiseaseFinding()));
        }
        audit.record(userId, AuditService.CANDIDATES_EXPORT, null, null, out.size() + " candidates");
        return new CandidateSet(out, notInStock);
    }

    // ---------------------------------------------------------------- helpers

    private Signoff toSignoff(CaseSignoff s, Map<Long, String> names) {
        return new Signoff(s.getId(), s.getConfirmedGrade(), s.getDiseaseFinding(), s.getEcd(), s.getCv(),
                s.getHexPercent(), cipher.decrypt(s.getNotesEnc(), CaseSignoff.NOTES, s.getId()), s.getSignedBy(),
                names.get(s.getSignedBy()), s.getCaseAnalysisId(), s.getCreatedAt());
    }

    private Map<Long, String> names(List<CaseSignoff> found) {
        return users.findAllById(found.stream().map(CaseSignoff::getSignedBy).distinct().toList()).stream()
                .collect(Collectors.toMap(AppUser::getId, u -> Stream.of(u.getFullName(), u.getUsername())
                        .filter(n -> n != null && !n.isBlank()).findFirst().orElse("(unknown)"), (a, b) -> a));
    }
}
