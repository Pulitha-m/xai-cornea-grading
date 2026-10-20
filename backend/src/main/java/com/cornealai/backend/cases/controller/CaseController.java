package com.cornealai.backend.cases.controller;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisRequest;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisResponse;
import com.cornealai.backend.cases.dto.CaseDtos.CaseDetails;
import com.cornealai.backend.cases.dto.CaseDtos.CaseImage;
import com.cornealai.backend.cases.dto.CaseDtos.CaseResponse;
import com.cornealai.backend.cases.dto.CaseDtos.CreateCaseRequest;
import com.cornealai.backend.cases.dto.CaseDtos.RunDetail;
import com.cornealai.backend.cases.dto.CaseDtos.RunSummary;
import com.cornealai.backend.cases.service.CaseAnalysisService;
import com.cornealai.backend.cases.service.CaseHistoryService;
import com.cornealai.backend.cases.service.CaseService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

/**
 * The donor case workspace. A case is opened by tissue ID (e.g. 12656R) and then addressed by its UUID;
 * its details are entered once, its images are stored encrypted, and analyses run on the case with
 * inputs from those details. Any clinical user (analysis:run) may work on any case.
 */
@RestController
@RequestMapping("/api/cases")
@PreAuthorize("hasAuthority('analysis:run')")
public class CaseController {

    private final CaseService cases;
    private final CaseAnalysisService analyses;
    private final CaseHistoryService history;

    public CaseController(CaseService cases, CaseAnalysisService analyses, CaseHistoryService history) {
        this.cases = cases;
        this.analyses = analyses;
        this.history = history;
    }

    /** Opens the case for a tissue ID: 201 when it was created now, 200 when it already existed. */
    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CaseResponse> open(@Valid @RequestBody CreateCaseRequest request,
                                             @AuthenticationPrincipal AppUserDetails user) {
        CaseService.Opened opened = cases.open(request.tissueId(), user.getId());
        return ResponseEntity.status(opened.created() ? HttpStatus.CREATED : HttpStatus.OK).body(opened.body());
    }

    /** {@code ?tissueId=12656R} finds one case; without it, the 20 most recently updated cases. */
    @GetMapping
    public List<CaseResponse> find(@RequestParam(required = false) String tissueId) {
        return tissueId == null ? cases.recent() : List.of(cases.findByTissueId(tissueId));
    }

    @GetMapping("/{caseId}")
    public CaseResponse get(@PathVariable UUID caseId) {
        return cases.get(caseId);
    }

    @PutMapping(path = "/{caseId}/details", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CaseResponse updateDetails(@PathVariable UUID caseId, @Valid @RequestBody CaseDetails details) {
        return cases.updateDetails(caseId, details);
    }

    @PostMapping(path = "/{caseId}/images", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ImageUploadResponse> uploadImage(@PathVariable UUID caseId,
                                                           @RequestPart("file") MultipartFile file,
                                                           @AuthenticationPrincipal AppUserDetails user) {
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "IMAGE_DECODE_FAILED", "file",
                    "The upload could not be read. Try again.");
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(cases.uploadImage(caseId, data, user.getId()));
    }

    @GetMapping("/{caseId}/images")
    public List<CaseImage> images(@PathVariable UUID caseId) {
        return cases.images(caseId);
    }

    /** The decrypted image, for viewing only: never cached, never sniffed as another type. */
    @GetMapping("/{caseId}/images/{imageId}/content")
    public ResponseEntity<byte[]> imageContent(@PathVariable UUID caseId, @PathVariable UUID imageId) {
        AnalysisImage image = cases.requireImage(caseId, imageId);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(image.getContentType()))
                .cacheControl(CacheControl.noStore())
                .header("X-Content-Type-Options", "nosniff")
                .header("Content-Disposition", "inline")
                .body(cases.imageContent(image));
    }

    @PostMapping(path = "/{caseId}/analyses", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CaseAnalysisResponse analyze(@PathVariable UUID caseId, @Valid @RequestBody CaseAnalysisRequest request,
                                        @AuthenticationPrincipal AppUserDetails user) {
        return analyses.analyze(caseId, request, user.getId());
    }

    @GetMapping("/{caseId}/runs")
    public List<RunSummary> runs(@PathVariable UUID caseId) {
        return history.runs(caseId);
    }

    @GetMapping("/{caseId}/runs/{module}/{runId}")
    public RunDetail run(@PathVariable UUID caseId, @PathVariable String module, @PathVariable UUID runId) {
        return history.run(caseId, module, runId);
    }
}
