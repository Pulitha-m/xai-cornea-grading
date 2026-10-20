package com.cornealai.backend.transplant;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.FollowupVisit;
import com.cornealai.backend.analysis.dto.recommendation.MatchCandidate;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import com.cornealai.backend.analysis.repository.RecommendationAnalysisRunRepository;
import com.cornealai.backend.analysis.service.RecommendationAnalysisService;
import com.cornealai.backend.audit.AuditService;
import com.cornealai.backend.cases.dto.CaseDtos.MatchCandidateView;
import com.cornealai.backend.cases.entity.CaseSignoff;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.CaseSignoffRepository;
import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.cases.service.SignoffService;
import com.cornealai.backend.transplant.TransplantDtos.AllocateRequest;
import com.cornealai.backend.transplant.TransplantDtos.CaseMatchRequest;
import com.cornealai.backend.transplant.TransplantDtos.CaseMatchResponse;
import com.cornealai.backend.transplant.TransplantDtos.FollowupSummary;
import com.cornealai.backend.transplant.TransplantDtos.GraftFollowup;
import com.cornealai.backend.transplant.TransplantDtos.GraftUpdate;
import com.cornealai.backend.transplant.TransplantDtos.GraftView;
import com.cornealai.backend.transplant.TransplantDtos.VisitRequest;
import com.cornealai.backend.transplant.TransplantDtos.VisitView;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

/**
 * Connects donor cases to the recommendation module. Matching ranks the signed-off corneas in stock
 * (sent by case UUID, never by tissue ID); allocating a ranked cornea to a recipient request creates
 * its graft; the graft's 3-, 6- and 12-month visits, with the donor case and its confirmed values, are
 * the inputs of the post-transplant follow-up recommendation, kept with the graft.
 */
@Service
public class TransplantService {

    private static final List<Integer> VISIT_MONTHS = List.of(3, 6, 12);

    private final SignoffService signoffs;
    private final CaseSignoffRepository signoffRepository;
    private final DonorCaseService donorCases;
    private final GraftRepository grafts;
    private final GraftVisitRepository visits;
    private final RecommendationAnalysisService recommendation;
    private final RecommendationAnalysisRunRepository recommendationRuns;
    private final Validator validator;
    private final AuditService audit;
    private final ObjectMapper objectMapper;

    public TransplantService(SignoffService signoffs, CaseSignoffRepository signoffRepository,
                             DonorCaseService donorCases, GraftRepository grafts, GraftVisitRepository visits,
                             RecommendationAnalysisService recommendation,
                             RecommendationAnalysisRunRepository recommendationRuns, Validator validator,
                             AuditService audit, ObjectMapper objectMapper) {
        this.signoffs = signoffs;
        this.signoffRepository = signoffRepository;
        this.donorCases = donorCases;
        this.grafts = grafts;
        this.visits = visits;
        this.recommendation = recommendation;
        this.recommendationRuns = recommendationRuns;
        this.validator = validator;
        this.audit = audit;
        this.objectMapper = objectMapper;
    }

    // ---------------------------------------------------------------- matching

    /** Ranks the signed-off corneas in stock for the request. Positive serology is never ranked. */
    public CaseMatchResponse match(CaseMatchRequest request, Long userId) {
        SignoffService.CandidateSet set = signoffs.candidateSet(userId);
        if (set.inStock().isEmpty()) {
            throw new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "NO_CANDIDATES", null,
                    "No signed-off cornea is in stock. Sign off cases before matching.");
        }
        Map<String, String> tissueIds = new LinkedHashMap<>();
        List<MatchCandidate> candidates = new ArrayList<>();
        for (MatchCandidateView c : set.inStock()) {
            tissueIds.put(c.recordId(), c.tissueId());
            candidates.add(new MatchCandidate(c.recordId(), c.grade(), c.ecd(), c.cv(), c.hex(), c.donorAge(),
                    c.deathToPreservationH(), c.daysInStorage(), c.serologyClear()));
        }
        MatchResponse match = recommendation.match(new MatchRequest(request.request(), candidates, request.topK(),
                request.weights(), request.method()), userId);
        return new CaseMatchResponse(match, tissueIds, candidates.size(), set.notInStock());
    }

    // ---------------------------------------------------------------- grafts

    /** Allocates a signed-off cornea to a recipient request (doctors). It then leaves the stock. */
    public GraftView allocate(AllocateRequest request, Long userId) {
        DonorCase donorCase = donorCases.require(request.caseId());
        if (signoffRepository.findFirstByDonorCaseIdOrderByCreatedAtDesc(donorCase.getId()).isEmpty()) {
            throw conflict("NOT_SIGNED_OFF", "Only a signed-off cornea can be allocated. Sign off the case first.");
        }
        if (Boolean.FALSE.equals(donorCase.getSerologyClear())) {
            throw conflict("SEROLOGY_POSITIVE", "This cornea has a positive serology result and cannot be transplanted.");
        }
        if (grafts.existsByDonorCaseId(donorCase.getId())) {
            throw conflict("ALREADY_ALLOCATED", "This cornea has already been allocated.");
        }
        if (request.matchRunId() != null && recommendationRuns.findById(request.matchRunId())
                .filter(r -> RecommendationAnalysisRun.MATCH.equals(r.getKind())).isEmpty()) {
            throw new AnalysisRejectedException(HttpStatus.NOT_FOUND, "MATCH_NOT_FOUND", "matchRunId",
                    "The matching run was not found.");
        }
        Graft graft = new Graft();
        graft.setId(UUID.randomUUID());
        graft.setDonorCaseId(donorCase.getId());
        graft.setRequestId(request.requestId().strip());
        graft.setProcedure(request.procedure());
        graft.setIndication(request.indication().strip());
        graft.setSurgeryDate(request.surgeryDate());
        graft.setMatchRunId(request.matchRunId());
        graft.setAllocatedBy(userId);
        grafts.saveAndFlush(graft);
        audit.record(userId, AuditService.GRAFT_ALLOCATE, "case", donorCase.getId(),
                "request " + graft.getRequestId() + ", " + graft.getProcedure());
        return view(graft);
    }

    /** All grafts, newest first, or the graft of one case. Shows tissue IDs, so it is audited. */
    public List<GraftView> grafts(UUID caseId, Long userId) {
        List<Graft> found = caseId == null ? grafts.findAllByOrderByCreatedAtDesc()
                : grafts.findByDonorCaseId(caseId).map(List::of).orElse(List.of());
        audit.record(userId, AuditService.CASE_LIST, caseId == null ? null : "case", caseId, found.size() + " grafts");
        return found.stream().map(this::view).toList();
    }

    public GraftView graft(UUID graftId, Long userId) {
        Graft graft = require(graftId);
        audit.record(userId, AuditService.CASE_VIEW, "case", graft.getDonorCaseId(), "graft");
        return view(graft);
    }

    public GraftView update(UUID graftId, GraftUpdate update, Long userId) {
        Graft graft = require(graftId);
        if (update.indication() != null) {
            graft.setIndication(update.indication().strip());
        }
        if (update.surgeryDate() != null) {
            graft.setSurgeryDate(update.surgeryDate());
        }
        if (update.rejectionBy12m() != null) {
            graft.setRejectionBy12m(update.rejectionBy12m());
        }
        grafts.saveAndFlush(graft);
        audit.record(userId, AuditService.GRAFT_UPDATE, "case", graft.getDonorCaseId(), "graft details");
        return view(graft);
    }

    /** Records (or corrects) the 3-, 6- or 12-month visit. */
    public GraftView recordVisit(UUID graftId, int month, VisitRequest request, Long userId) {
        if (!VISIT_MONTHS.contains(month)) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "month",
                    "Follow-up visits are at 3, 6 and 12 months.");
        }
        Graft graft = require(graftId);
        GraftVisit visit = visits.findByGraftIdAndMonth(graftId, month).orElseGet(() -> {
            GraftVisit created = new GraftVisit();
            created.setId(UUID.randomUUID());
            created.setGraftId(graftId);
            created.setMonth(month);
            return created;
        });
        visit.setEcd(request.ecd());
        visit.setCv(request.cv());
        visit.setHex(request.hex());
        visit.setVisitDate(request.visitDate());
        visit.setRecordedBy(userId);
        visits.saveAndFlush(visit);
        audit.record(userId, AuditService.GRAFT_UPDATE, "case", graft.getDonorCaseId(), month + "-month visit");
        return view(graft);
    }

    // ---------------------------------------------------------------- follow-up

    /** The follow-up recommendation for the graft, from its visits and the donor case. */
    public GraftFollowup followup(UUID graftId, Long userId) {
        Graft graft = require(graftId);
        GraftView view = view(graft);
        if (!view.missing().isEmpty()) {
            throw new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "FOLLOWUP_INPUT_MISSING", null,
                    "Still needed for the follow-up recommendation: " + String.join(", ", view.missing()) + ".");
        }
        Map<Integer, VisitView> byMonth = new LinkedHashMap<>();
        view.visits().forEach(v -> byMonth.put(v.month(), v));
        FollowupRequest request = new FollowupRequest(graft.getId().toString(), graft.getProcedure(),
                graft.getIndication(), view.donorAge(), view.baselineEcd(), view.baselineCv(), view.baselineHex(),
                visit(byMonth.get(3)), visit(byMonth.get(6)), visit(byMonth.get(12)), graft.getRejectionBy12m());
        Set<ConstraintViolation<FollowupRequest>> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            List<String> problems = violations.stream()
                    .map(v -> v.getPropertyPath() + " " + v.getMessage()).sorted().toList();
            throw new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "FOLLOWUP_INPUT_INVALID", null,
                    "The graft's values are outside what the follow-up model accepts: " + String.join("; ", problems) + ".");
        }
        audit.record(userId, AuditService.FOLLOWUP_RUN, "case", graft.getDonorCaseId(), null);
        FollowupResponse result = recommendation.followup(request, userId);
        RecommendationAnalysisRun run = recommendationRuns.findById(result.analysisId()).orElseThrow();
        return new GraftFollowup(summary(run), request, result);
    }

    public List<FollowupSummary> followups(UUID graftId) {
        require(graftId);
        return runsOf(graftId).stream().map(TransplantService::summary).toList();
    }

    public GraftFollowup followupRun(UUID graftId, UUID runId, Long userId) {
        require(graftId);
        RecommendationAnalysisRun run = runsOf(graftId).stream().filter(r -> r.getId().equals(runId)).findFirst()
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "RUN_NOT_FOUND", "runId",
                        "The follow-up recommendation was not found for this graft."));
        audit.record(userId, AuditService.RUN_VIEW, "followup_run", runId, null);
        FollowupRequest request = run.getInputsJson() == null ? null
                : objectMapper.readValue(run.getInputsJson(), FollowupRequest.class);
        FollowupResponse result = run.getResultJson() == null ? null
                : objectMapper.readValue(run.getResultJson(), FollowupResponse.class);
        return new GraftFollowup(summary(run), request, result);
    }

    // ---------------------------------------------------------------- helpers

    private GraftView view(Graft graft) {
        DonorCase donorCase = donorCases.require(graft.getDonorCaseId());
        Optional<CaseSignoff> signoff = signoffRepository.findFirstByDonorCaseIdOrderByCreatedAtDesc(donorCase.getId());
        Double ecd = signoff.map(CaseSignoff::getEcd).orElse(null);
        Double cv = signoff.map(CaseSignoff::getCv).orElse(null);
        Double hex = signoff.map(CaseSignoff::getHexPercent).orElse(null);
        Double baselineEcd = ecd != null ? ecd : donorCase.getEcd();
        Double baselineCv = cv != null ? cv : donorCase.getCv();
        Double baselineHex = hex != null ? hex : donorCase.getHexPercent();
        Double donorAge = donorCase.getDonorAgeYears() == null ? null : donorCase.getDonorAgeYears().doubleValue();

        List<VisitView> recorded = visits.findByGraftIdOrderByMonth(graft.getId()).stream()
                .map(v -> new VisitView(v.getMonth(), v.getEcd(), v.getCv(), v.getHex(), v.getVisitDate())).toList();
        List<String> missing = new ArrayList<>();
        if (donorAge == null) missing.add("donor age (case details)");
        if (baselineEcd == null) missing.add("baseline ECD");
        if (baselineCv == null) missing.add("baseline CV");
        if (baselineHex == null) missing.add("baseline HEX");
        if (recorded.stream().noneMatch(v -> v.month() == 6)) missing.add("6-month visit");
        if (recorded.stream().noneMatch(v -> v.month() == 12)) missing.add("12-month visit");

        FollowupSummary latest = runsOf(graft.getId()).stream().findFirst().map(TransplantService::summary).orElse(null);
        return new GraftView(graft.getId(), donorCase.getId(), donorCases.tissueNumberOf(donorCase).value(),
                graft.getRequestId(), graft.getProcedure(), graft.getIndication(), graft.getSurgeryDate(),
                graft.getRejectionBy12m(), donorAge, baselineEcd, baselineCv, baselineHex, recorded, missing, latest,
                graft.getCreatedAt());
    }

    private List<RecommendationAnalysisRun> runsOf(UUID graftId) {
        return recommendationRuns.findBySubjectIdAndKindOrderByCreatedAtDesc(graftId.toString(),
                RecommendationAnalysisRun.FOLLOWUP).stream()
                .sorted(Comparator.comparing(RecommendationAnalysisRun::getCreatedAt).reversed()).toList();
    }

    private static FollowupSummary summary(RecommendationAnalysisRun run) {
        return new FollowupSummary(run.getId(), run.getStatus(), run.getErrorCode(), run.getAlert(),
                run.getNextVisitMonths(), run.getCreatedAt());
    }

    private static FollowupVisit visit(VisitView v) {
        return v == null ? null : new FollowupVisit(v.ecd(), v.cv(), v.hex());
    }

    private Graft require(UUID graftId) {
        return grafts.findById(graftId).orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND,
                "GRAFT_NOT_FOUND", "graftId", "The graft was not found."));
    }

    private static AnalysisRejectedException conflict(String code, String message) {
        return new AnalysisRejectedException(HttpStatus.CONFLICT, code, "caseId", message);
    }
}
