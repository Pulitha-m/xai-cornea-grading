package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.dto.recommendation.RecommendationRuns.RunDetail;
import com.cornealai.backend.analysis.dto.recommendation.RecommendationRuns.RunPage;
import com.cornealai.backend.analysis.service.RecommendationAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import com.cornealai.backend.security.Permission;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.UUID;

/**
 * Recommendation (Member 4), decision support for a clinician:
 * POST /match ranks the corneas in stock for a recipient request (positive serology is never ranked);
 * POST /followup gives the alert level, next visit and review prompts for a graft at its 12-month visit;
 * GET /runs and /runs/{id} list and reopen saved runs.
 */
@RestController
@RequestMapping("/api/analysis/recommendation")
public class RecommendationAnalysisController {

    private final RecommendationAnalysisService recommendationAnalysisService;

    public RecommendationAnalysisController(RecommendationAnalysisService recommendationAnalysisService) {
        this.recommendationAnalysisService = recommendationAnalysisService;
    }

    @PostMapping(path = "/match", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public MatchResponse match(
            @Valid @RequestBody MatchRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return recommendationAnalysisService.match(request, user.getId());
    }

    @PostMapping(path = "/followup", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public FollowupResponse followup(
            @Valid @RequestBody FollowupRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return recommendationAnalysisService.followup(request, user.getId());
    }

    /** Previous runs of one kind ("match" or "followup"), newest first; {@code subject} filters by request or graft ID. */
    @GetMapping("/runs")
    @PreAuthorize("hasAuthority('analysis:run')")
    public RunPage runs(
            @RequestParam String kind,
            @RequestParam(required = false) String subject,
            @RequestParam(required = false) Instant before,
            @RequestParam(required = false) Integer limit,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return recommendationAnalysisService.runs(kind, subject, before, limit, user.getId(), seesAllRuns(user));
    }

    @GetMapping("/runs/{runId}")
    @PreAuthorize("hasAuthority('analysis:run')")
    public RunDetail run(@PathVariable UUID runId, @AuthenticationPrincipal AppUserDetails user) {
        return recommendationAnalysisService.run(runId, user.getId(), seesAllRuns(user));
    }

    /** Matching runs carry serology status: only users with serology access see everyone's runs. */
    private static boolean seesAllRuns(AppUserDetails user) {
        String serology = Permission.SEROLOGY_ACCESS.authority();
        return user.getAuthorities().stream().anyMatch(a -> serology.equals(a.getAuthority()));
    }
}
