package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import com.cornealai.backend.analysis.repository.RecommendationAnalysisRunRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;
import java.util.function.Supplier;

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

    public RecommendationAnalysisService(
            RecommendationAnalysisRunRepository runs,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper
    ) {
        this.runs = runs;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
    }

    public MatchResponse match(MatchRequest request, Long userId) {
        RecommendationAnalysisRun run = newRun(RecommendationAnalysisRun.MATCH, request.request().requestId(), userId);
        run.setInputsJson(objectMapper.writeValueAsString(request));
        return record(run, () -> {
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

    private static AnalysisRejectedException failed(String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null, message);
    }
}
