package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchCandidate;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchWeights;
import com.cornealai.backend.analysis.dto.recommendation.RecommendationRuns.RunDetail;
import com.cornealai.backend.analysis.dto.recommendation.RecommendationRuns.RunPage;
import com.cornealai.backend.analysis.dto.recommendation.RecommendationRuns.RunSummary;
import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import com.cornealai.backend.analysis.repository.RecommendationAnalysisRunRepository;
import com.cornealai.backend.user.repository.AppUserRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Supplier;
import java.util.stream.Collectors;

/**
 * Recommendation (Member 4): donor-tissue ranking for a recipient request and the post-transplant follow-up
 * recommendation at the 12-month visit. Both are decision support for a clinician. Every attempt is recorded,
 * including rejections, as for the other analysis modules.
 */
@Service
public class RecommendationAnalysisService {

    private final RecommendationAnalysisRunRepository runs;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;
    private final AppUserRepository users;

    public RecommendationAnalysisService(
            RecommendationAnalysisRunRepository runs,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper,
            AppUserRepository users
    ) {
        this.runs = runs;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
        this.users = users;
    }

    public MatchResponse match(MatchRequest request, Long userId) {
        RecommendationAnalysisRun run = newRun(RecommendationAnalysisRun.MATCH, request.request().requestId(), userId);
        run.setInputsJson(objectMapper.writeValueAsString(request));
        return record(run, () -> {
            checkMatchRequest(request);
            MatchResponse result = mlServiceClient.recommendMatch(request);
            if (result == null || result.ranked() == null) {
                throw failed("The donor-tissue ranking could not be completed. Try again later.");
            }
            MatchResponse response = result.withAnalysisId(run.getId());
            run.setMethodUsed(response.methodUsed());
            run.setTopRecordId(response.ranked().isEmpty() ? null : response.ranked().getFirst().recordId());
            return response;
        });
    }

    public FollowupResponse followup(FollowupRequest request, Long userId) {
        RecommendationAnalysisRun run = newRun(RecommendationAnalysisRun.FOLLOWUP, request.graftId(), userId);
        run.setInputsJson(objectMapper.writeValueAsString(request));
        return record(run, () -> {
            FollowupResponse result = mlServiceClient.recommendFollowup(request);
            if (result == null || result.alert() == null || result.nextVisitMonths() == null) {
                throw failed("The follow-up recommendation could not be completed. Try again later.");
            }
            FollowupResponse response = result.withAnalysisId(run.getId());
            run.setAlert(response.alert());
            run.setNextVisitMonths(response.nextVisitMonths());
            return response;
        });
    }

    // ---------------------------------------------------------------- previous runs

    /**
     * Saved runs of one kind ("match" or "followup"), newest first, optionally for one request or graft ID.
     * Match runs carry serology status, so users with serology access see everyone's runs and others only
     * their own (which hold only values they entered themselves).
     */
    public RunPage runs(String kind, String subjectId, Instant before, Integer limit, Long userId, boolean seeAll) {
        requireKind(kind);
        int size = Math.clamp(limit == null ? 10 : limit, 1, 50);
        Instant cursor = before == null ? Instant.now().plusSeconds(1) : before;
        PageRequest page = PageRequest.of(0, size + 1);  // one extra tells whether older runs exist
        String subject = subjectId == null || subjectId.isBlank() ? null : subjectId.strip();
        List<RecommendationAnalysisRun> found;
        if (seeAll) {
            found = subject == null
                    ? runs.findByKindAndCreatedAtBeforeOrderByCreatedAtDesc(kind, cursor, page)
                    : runs.findByKindAndSubjectIdIgnoreCaseAndCreatedAtBeforeOrderByCreatedAtDesc(kind, subject, cursor, page);
        } else {
            found = subject == null
                    ? runs.findByKindAndRequestedByAndCreatedAtBeforeOrderByCreatedAtDesc(kind, userId, cursor, page)
                    : runs.findByKindAndRequestedByAndSubjectIdIgnoreCaseAndCreatedAtBeforeOrderByCreatedAtDesc(
                            kind, userId, subject, cursor, page);
        }
        List<RecommendationAnalysisRun> shown = found.subList(0, Math.min(size, found.size()));
        Map<Long, String> names = names(shown);
        Instant nextBefore = found.size() > size ? shown.getLast().getCreatedAt() : null;
        return new RunPage(shown.stream().map(r -> summary(r, names)).toList(), nextBefore);
    }

    /** One saved run with its request and result; 404 if it does not exist or the caller may not see it. */
    public RunDetail run(UUID runId, Long userId, boolean seeAll) {
        RecommendationAnalysisRun run = runs.findById(runId)
                .filter(r -> seeAll || r.getRequestedBy().equals(userId))
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "RUN_NOT_FOUND", null,
                        "The run was not found."));
        return new RunDetail(summary(run, names(List.of(run))), json(run.getInputsJson()), json(run.getResultJson()));
    }

    private static void requireKind(String kind) {
        if (!RecommendationAnalysisRun.MATCH.equals(kind) && !RecommendationAnalysisRun.FOLLOWUP.equals(kind)) {
            throw invalid("INVALID_REQUEST", "kind", "kind must be 'match' or 'followup'.");
        }
    }

    private Map<Long, String> names(List<RecommendationAnalysisRun> list) {
        Set<Long> ids = list.stream().map(RecommendationAnalysisRun::getRequestedBy).collect(Collectors.toSet());
        Map<Long, String> out = new HashMap<>();
        users.findAllById(ids).forEach(u -> out.put(u.getId(),
                u.getFullName() == null || u.getFullName().isBlank() ? u.getUsername() : u.getFullName()));
        return out;
    }

    private static RunSummary summary(RecommendationAnalysisRun r, Map<Long, String> names) {
        return new RunSummary(r.getId(), r.getKind(), r.getSubjectId(), r.getStatus(), r.getErrorCode(),
                r.getMethodUsed(), r.getTopRecordId(), r.getAlert(), r.getNextVisitMonths(),
                names.get(r.getRequestedBy()), r.getCreatedAt());
    }

    private JsonNode json(String text) {
        return text == null ? null : objectMapper.readTree(text);
    }

    /** Checks that span several fields: each tissue ID once per request, and at least one MCDA weight above 0. */
    private static void checkMatchRequest(MatchRequest request) {
        Set<String> seen = new HashSet<>();
        Set<String> duplicates = new LinkedHashSet<>();
        for (MatchCandidate c : request.candidates()) {
            if (!seen.add(c.recordId().strip().toUpperCase(Locale.ROOT))) {
                duplicates.add(c.recordId().strip());
            }
        }
        if (!duplicates.isEmpty()) {
            throw invalid("DUPLICATE_TISSUE_ID", "candidates",
                    "Each tissue ID can appear only once: " + String.join(", ", duplicates) + ".");
        }
        MatchWeights w = request.weights();
        if (w != null) {
            List<Double> values = Arrays.asList(w.gradeFit(), w.endothelium(), w.serology(), w.freshness(),
                    w.surgeryCompatibility());
            if (values.stream().allMatch(v -> v != null && v == 0)) {
                throw invalid("INVALID_WEIGHTS", "weights", "At least one weight must be above 0.");
            }
        }
    }

    private RecommendationAnalysisRun newRun(String kind, String subjectId, Long userId) {
        RecommendationAnalysisRun run = new RecommendationAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setKind(kind);
        run.setSubjectId(subjectId.trim());
        run.setRequestedBy(userId);
        return run;
    }

    private <T> T record(RecommendationAnalysisRun run, Supplier<T> call) {
        try {
            T response = call.get();
            run.setStatus("completed");
            run.setResultJson(objectMapper.writeValueAsString(response));
            runs.save(run);
            return response;
        } catch (AnalysisRejectedException e) {
            run.setStatus("rejected");
            run.setErrorCode(e.getCode());
            runs.save(run);
            throw e;
        } catch (RuntimeException e) {
            run.setStatus("failed");
            run.setErrorCode("INTERNAL_ERROR");
            try {
                runs.save(run);
            } catch (RuntimeException ignored) {
                // The database itself failed; the original error is what matters.
            }
            throw e;
        }
    }

    private static AnalysisRejectedException invalid(String code, String field, String message) {
        return new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, code, field, message);
    }

    private static AnalysisRejectedException failed(String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null, message);
    }
}
