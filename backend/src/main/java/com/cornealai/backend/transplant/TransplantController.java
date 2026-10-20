package com.cornealai.backend.transplant;

import com.cornealai.backend.security.AppUserDetails;
import com.cornealai.backend.transplant.TransplantDtos.AllocateRequest;
import com.cornealai.backend.transplant.TransplantDtos.CaseMatchRequest;
import com.cornealai.backend.transplant.TransplantDtos.CaseMatchResponse;
import com.cornealai.backend.transplant.TransplantDtos.FollowupSummary;
import com.cornealai.backend.transplant.TransplantDtos.GraftFollowup;
import com.cornealai.backend.transplant.TransplantDtos.GraftUpdate;
import com.cornealai.backend.transplant.TransplantDtos.GraftView;
import com.cornealai.backend.transplant.TransplantDtos.VisitRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * Transplant workflow on donor cases: rank the signed-off corneas in stock for a recipient request
 * (doctors, as candidates carry serology status), allocate one (doctors), then record the graft's
 * follow-up visits and get the post-transplant follow-up recommendation (doctors and nurses).
 */
@RestController
@RequestMapping("/api/transplants")
@PreAuthorize("hasAuthority('analysis:run')")
public class TransplantController {

    private final TransplantService transplants;

    public TransplantController(TransplantService transplants) {
        this.transplants = transplants;
    }

    @PostMapping(path = "/match", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('serology:access')")
    public CaseMatchResponse match(@Valid @RequestBody CaseMatchRequest request,
                                   @AuthenticationPrincipal AppUserDetails user) {
        return transplants.match(request, user.getId());
    }

    @PostMapping(path = "/grafts", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('case:signoff')")
    public ResponseEntity<GraftView> allocate(@Valid @RequestBody AllocateRequest request,
                                              @AuthenticationPrincipal AppUserDetails user) {
        return ResponseEntity.status(HttpStatus.CREATED).body(transplants.allocate(request, user.getId()));
    }

    /** All grafts, newest first; {@code caseId} gives the graft of one case (empty list if not transplanted). */
    @GetMapping("/grafts")
    public List<GraftView> grafts(@RequestParam(required = false) UUID caseId,
                                  @AuthenticationPrincipal AppUserDetails user) {
        return transplants.grafts(caseId, user.getId());
    }

    @GetMapping("/grafts/{graftId}")
    public GraftView graft(@PathVariable UUID graftId, @AuthenticationPrincipal AppUserDetails user) {
        return transplants.graft(graftId, user.getId());
    }

    @PutMapping(path = "/grafts/{graftId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public GraftView update(@PathVariable UUID graftId, @Valid @RequestBody GraftUpdate update,
                            @AuthenticationPrincipal AppUserDetails user) {
        return transplants.update(graftId, update, user.getId());
    }

    @PutMapping(path = "/grafts/{graftId}/visits/{month}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public GraftView recordVisit(@PathVariable UUID graftId, @PathVariable int month,
                                 @Valid @RequestBody VisitRequest request,
                                 @AuthenticationPrincipal AppUserDetails user) {
        return transplants.recordVisit(graftId, month, request, user.getId());
    }

    @PostMapping("/grafts/{graftId}/followups")
    public GraftFollowup followup(@PathVariable UUID graftId, @AuthenticationPrincipal AppUserDetails user) {
        return transplants.followup(graftId, user.getId());
    }

    @GetMapping("/grafts/{graftId}/followups")
    public List<FollowupSummary> followups(@PathVariable UUID graftId) {
        return transplants.followups(graftId);
    }

    @GetMapping("/grafts/{graftId}/followups/{runId}")
    public GraftFollowup followupRun(@PathVariable UUID graftId, @PathVariable UUID runId,
                                     @AuthenticationPrincipal AppUserDetails user) {
        return transplants.followupRun(graftId, runId, user.getId());
    }
}
