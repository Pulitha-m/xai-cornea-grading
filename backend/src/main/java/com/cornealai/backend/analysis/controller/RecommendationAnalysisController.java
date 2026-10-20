package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.service.RecommendationAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * Recommendation (Member 4), decision support for a clinician:
 * POST /match ranks the corneas in stock for a recipient request (positive serology is never ranked);
 * POST /followup gives the alert level, next visit and review prompts for a graft at its 12-month visit.
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
}
