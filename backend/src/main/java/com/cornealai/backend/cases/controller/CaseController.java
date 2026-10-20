package com.cornealai.backend.cases.controller;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.cases.importer.CaseImportFile;
import com.cornealai.backend.cases.importer.CaseImportService;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisRequest;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisResponse;
import com.cornealai.backend.cases.dto.CaseDtos.CaseDetails;
import com.cornealai.backend.cases.dto.CaseDtos.CaseImage;
import com.cornealai.backend.cases.dto.CaseDtos.CaseResponse;
import com.cornealai.backend.cases.dto.CaseDtos.CreateCaseRequest;
import com.cornealai.backend.cases.dto.CaseDtos.MatchCandidateView;
import com.cornealai.backend.cases.dto.CaseDtos.ModuleRunPage;
import com.cornealai.backend.cases.dto.CaseDtos.Serology;
import com.cornealai.backend.cases.dto.CaseDtos.Signoff;
import com.cornealai.backend.cases.dto.CaseDtos.SignoffRequest;
import com.cornealai.backend.cases.dto.CaseDtos.RunDetail;
import com.cornealai.backend.cases.dto.CaseDtos.RunSummary;
import com.cornealai.backend.cases.service.CaseAnalysisService;
import com.cornealai.backend.cases.service.CaseHistoryService;
import com.cornealai.backend.cases.service.CaseService;
import com.cornealai.backend.cases.service.SignoffService;
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
import java.nio.charset.StandardCharsets;
import java.time.Instant;
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
    private final SignoffService signoffService;
    private final CaseImportService importer;

    public CaseController(CaseService cases, CaseAnalysisService analyses, CaseHistoryService history,
                          SignoffService signoffService, CaseImportService importer) {
        this.importer = importer;
        this.signoffService = signoffService;
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
    public List<CaseResponse> find(@RequestParam(required = false) String tissueId,
                                   @AuthenticationPrincipal AppUserDetails user) {
        return tissueId == null ? cases.recent(user.getId()) : List.of(cases.findByTissueId(tissueId, user.getId()));
    }

    @GetMapping("/{caseId}")
    public CaseResponse get(@PathVariable UUID caseId, @AuthenticationPrincipal AppUserDetails user) {
        return cases.get(caseId, user.getId());
    }

    @PutMapping(path = "/{caseId}/details", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CaseResponse updateDetails(@PathVariable UUID caseId, @Valid @RequestBody CaseDetails details,
                                      @AuthenticationPrincipal AppUserDetails user) {
        return cases.updateDetails(caseId, details, user.getId());
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
    public ResponseEntity<byte[]> imageContent(@PathVariable UUID caseId, @PathVariable UUID imageId,
                                               @AuthenticationPrincipal AppUserDetails user) {
        AnalysisImage image = cases.requireImage(caseId, imageId);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(image.getContentType()))
                .cacheControl(CacheControl.noStore())
                .header("X-Content-Type-Options", "nosniff")
                .header("Content-Disposition", "inline")
                .body(cases.imageContent(image, user.getId()));
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
    public RunDetail run(@PathVariable UUID caseId, @PathVariable String module, @PathVariable UUID runId,
                         @AuthenticationPrincipal AppUserDetails user) {
        return history.run(caseId, module, runId, user.getId());
    }

    /**
     * Saved runs of one module (cellular, grading, disease, combined) across cases, newest first, for
     * the module pages; {@code tissueId} narrows to one case, {@code before} (from nextBefore) pages back.
     */
    @GetMapping("/runs")
    public ModuleRunPage moduleRuns(@RequestParam String module, @RequestParam(required = false) String tissueId,
                                    @RequestParam(required = false) Instant before,
                                    @RequestParam(required = false) Integer limit,
                                    @AuthenticationPrincipal AppUserDetails user) {
        return history.moduleRuns(module, tissueId, before, limit, user.getId());
    }

    // ---------------------------------------------------------------- bulk import

    /** A CSV template with every column the import reads, and one example row. */
    @GetMapping("/import/template")
    public ResponseEntity<byte[]> importTemplate() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
                .header("Content-Disposition", "attachment; filename=\"case-import-template.csv\"")
                .body(CaseImportFile.templateCsv().getBytes(StandardCharsets.UTF_8));
    }

    /**
     * Bulk import of cases from CSV or Excel (.xlsx). With {@code apply=false} (default) only checks the
     * file and reports what each row would do. With {@code apply=true} imports it in one transaction, and
     * only if no row has an error (422 with the report otherwise). {@code mode}: "create" skips existing
     * tissue IDs, "update" also updates their details with the row's non-blank values.
     */
    @PostMapping(path = "/import", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<CaseImportService.ImportReport> importCases(@RequestPart("file") MultipartFile file,
                                                                  @RequestParam(required = false) String mode,
                                                                  @RequestParam(defaultValue = "false") boolean apply,
                                                                  @AuthenticationPrincipal AppUserDetails user) {
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_IMPORT_FILE", "file",
                    "The upload could not be read. Try again.");
        }
        CaseImportService.Mode importMode = CaseImportService.mode(mode);
        if (!apply) {
            return ResponseEntity.ok(importer.check(file.getOriginalFilename(), data, importMode));
        }
        CaseImportService.ImportReport report = importer.apply(file.getOriginalFilename(), data, importMode, user.getId());
        return ResponseEntity.status(report.applied() ? HttpStatus.OK : HttpStatus.UNPROCESSABLE_CONTENT).body(report);
    }

    // ---------------------------------------------------------------- sign-off, serology, candidates

    /** All sign-offs of the case, newest first; any clinician may read them. */
    @GetMapping("/{caseId}/signoffs")
    public List<Signoff> signoffs(@PathVariable UUID caseId, @AuthenticationPrincipal AppUserDetails user) {
        return signoffService.signoffs(caseId, user.getId());
    }

    /** A specialist confirms the grade and findings (doctors only). Append-only. */
    @PostMapping(path = "/{caseId}/signoffs", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('case:signoff')")
    public ResponseEntity<Signoff> signOff(@PathVariable UUID caseId, @Valid @RequestBody SignoffRequest request,
                                           @AuthenticationPrincipal AppUserDetails user) {
        return ResponseEntity.status(HttpStatus.CREATED).body(signoffService.signOff(caseId, request, user.getId()));
    }

    /** Serology results (doctors only; every read and change is audited). */
    @GetMapping("/{caseId}/serology")
    @PreAuthorize("hasAuthority('serology:access')")
    public Serology serology(@PathVariable UUID caseId, @AuthenticationPrincipal AppUserDetails user) {
        return signoffService.serology(caseId, user.getId());
    }

    @PutMapping(path = "/{caseId}/serology", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('serology:access')")
    public Serology updateSerology(@PathVariable UUID caseId, @Valid @RequestBody Serology request,
                                   @AuthenticationPrincipal AppUserDetails user) {
        return signoffService.updateSerology(caseId, request, user.getId());
    }

    /** Signed-off corneas as recommendation candidates (confirmed values; carries serology status). */
    @GetMapping("/candidates")
    @PreAuthorize("hasAuthority('serology:access')")
    public List<MatchCandidateView> candidates(@AuthenticationPrincipal AppUserDetails user) {
        return signoffService.candidates(user.getId());
    }
}
