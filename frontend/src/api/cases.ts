import type { ImageUploadResponse } from "@/api/analysis"
import type { CellularAnalyzeResponse } from "@/api/cellular"
import type { DiseaseAnalyzeResponse } from "@/api/disease"
import type { GradingAnalyzeResponse } from "@/api/grading"
import { apiBlob, apiRequest, apiUpload } from "@/lib/api-client"

/**
 * Donor case workspace (/api/cases). A case is opened by tissue ID (e.g. 12656R) and then addressed by
 * its id; its details are entered once and every module analyses them. Any doctor or nurse may work on
 * any case. The tissue ID is stored encrypted on the server and shown only through these calls.
 */

export type CaseModule = "cellular" | "grading" | "disease"
export const CASE_MODULES: CaseModule[] = ["cellular", "grading", "disease"]

export const MODULE_LABELS: Record<CaseModule | "combined", string> = {
    cellular: "Cellular analysis",
    grading: "Cornea grading",
    disease: "Disease screening",
    combined: "AI analysis (combined)",
}

export interface CaseDetails {
    donorAgeYears: number | null
    deathToPreservationHours: number | null
    /** ISO date (yyyy-mm-dd). */
    preservationDate: string | null
    ecd: number | null
    cv: number | null
    hexPercent: number | null
    sd: number | null
    totalCellCount: number | null
    totalAreaUm2: number | null
    /** The 18 slit-lamp findings by grading feature name: 0/1, a category, or null (not recorded). */
    slitLamp: Record<string, number | string | null>
}

export interface DonorCase {
    id: string
    tissueId: string
    details: CaseDetails
    imageCount: number
    /** The current specialist sign-off, if any (notes are only in the sign-off list). */
    latestSignoff: SignoffSummary | null
    createdAt: string
    updatedAt: string
}

export const GRADES = ["A+", "A", "B", "C"] as const
/** Disease findings as the recommendation module uses them. */
export const DISEASE_FINDINGS = ["Normal", "Folds", "Guttata", "FECD", "Other"] as const

export interface SignoffSummary {
    confirmedGrade: string
    diseaseFinding: string
    signedByName: string | null
    createdAt: string
}

export interface SignoffRequest {
    confirmedGrade: string
    diseaseFinding: string
    ecd: number | null
    cv: number | null
    hexPercent: number | null
    notes: string | null
    caseAnalysisId: string | null
}

export interface Signoff extends Omit<SignoffRequest, "caseAnalysisId"> {
    id: string
    signedBy: number
    signedByName: string | null
    caseAnalysisId: string | null
    createdAt: string
}

export type SerologyResult = "Negative" | "Positive" | "Unknown"
export const SEROLOGY_TESTS = [
    { key: "hiv", label: "HIV" },
    { key: "hbv", label: "Hepatitis B (HBsAg)" },
    { key: "hcv", label: "Hepatitis C" },
    { key: "syphilis", label: "Syphilis" },
] as const

export interface Serology {
    hiv: SerologyResult | null
    hbv: SerologyResult | null
    hcv: SerologyResult | null
    syphilis: SerologyResult | null
    /** Derived: true only when all four are negative, false when any is positive, else null. */
    serologyClear: boolean | null
}

/** A signed-off cornea in the recommendation module's candidate fields (confirmed values only). */
export interface MatchCandidate {
    recordId: string
    tissueId: string
    grade: string
    ecd: number | null
    cv: number | null
    hex: number | null
    donorAge: number | null
    deathToPreservationH: number | null
    daysInStorage: number | null
    serologyClear: "Yes" | "No" | "Unknown"
    diseaseFinding: string
}

export interface CaseImage {
    id: string
    contentType: string
    sizeBytes: number
    width: number
    height: number
    uploadedBy: number
    uploadedAt: string
}

export interface ModuleOutcome<T> {
    /** "completed" (with result), "rejected" or "failed" (with errorCode and message). */
    status: "completed" | "rejected" | "failed"
    errorCode: string | null
    message: string | null
    result: T | null
}

export interface ConsistencyFlag {
    code: string
    message: string
}

export interface CaseAnalysisResponse {
    id: string
    tissueId: string
    imageId: string
    modules: {
        cellular?: ModuleOutcome<CellularAnalyzeResponse>
        grading?: ModuleOutcome<GradingAnalyzeResponse>
        disease?: ModuleOutcome<DiseaseAnalyzeResponse>
    }
    consistency: ConsistencyFlag[]
    createdAt: string
}

export interface RunSummary {
    id: string
    module: CaseModule | "combined"
    status: string
    errorCode: string | null
    imageId: string
    caseAnalysisId: string | null
    createdAt: string
    headline: Record<string, unknown>
}

export interface RunDetail {
    summary: RunSummary
    inputs: Record<string, unknown> | null
    result: Record<string, unknown> | null
}

export function openCase(tissueId: string): Promise<DonorCase> {
    return apiRequest<DonorCase>("/api/cases", { method: "POST", body: { tissueId } })
}

export function recentCases(): Promise<DonorCase[]> {
    return apiRequest<DonorCase[]>("/api/cases")
}

export function getCase(caseId: string): Promise<DonorCase> {
    return apiRequest<DonorCase>(`/api/cases/${encodeURIComponent(caseId)}`)
}

export function updateCaseDetails(caseId: string, details: CaseDetails): Promise<DonorCase> {
    return apiRequest<DonorCase>(`/api/cases/${encodeURIComponent(caseId)}/details`, { method: "PUT", body: details })
}

export function listCaseImages(caseId: string): Promise<CaseImage[]> {
    return apiRequest<CaseImage[]>(`/api/cases/${encodeURIComponent(caseId)}/images`)
}

export function uploadCaseImage(caseId: string, file: File, onProgress?: (fraction: number) => void): Promise<ImageUploadResponse> {
    const form = new FormData()
    form.append("file", file)
    return apiUpload<ImageUploadResponse>(`/api/cases/${encodeURIComponent(caseId)}/images`, form, { onProgress })
}

/** The decrypted image, fetched with the session's token (an <img src> could not send it). */
export function fetchCaseImage(caseId: string, imageId: string): Promise<Blob> {
    return apiBlob(`/api/cases/${encodeURIComponent(caseId)}/images/${encodeURIComponent(imageId)}/content`)
}

export function analyzeCase(
    caseId: string,
    request: { imageId: string; modules: CaseModule[]; forceDisease?: boolean },
): Promise<CaseAnalysisResponse> {
    return apiRequest<CaseAnalysisResponse>(`/api/cases/${encodeURIComponent(caseId)}/analyses`, { method: "POST", body: request })
}

export function listCaseRuns(caseId: string): Promise<RunSummary[]> {
    return apiRequest<RunSummary[]>(`/api/cases/${encodeURIComponent(caseId)}/runs`)
}

export function getCaseRun(caseId: string, module: RunSummary["module"], runId: string): Promise<RunDetail> {
    return apiRequest<RunDetail>(
        `/api/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(module)}/${encodeURIComponent(runId)}`,
    )
}

export function listSignoffs(caseId: string): Promise<Signoff[]> {
    return apiRequest<Signoff[]>(`/api/cases/${encodeURIComponent(caseId)}/signoffs`)
}

/** Doctors only (case:signoff). Append-only: a correction is a new sign-off. */
export function signOff(caseId: string, request: SignoffRequest): Promise<Signoff> {
    return apiRequest<Signoff>(`/api/cases/${encodeURIComponent(caseId)}/signoffs`, { method: "POST", body: request })
}

/** Doctors only (serology:access); every read and change is audited. */
export function getSerology(caseId: string): Promise<Serology> {
    return apiRequest<Serology>(`/api/cases/${encodeURIComponent(caseId)}/serology`)
}

export function updateSerology(caseId: string, serology: Omit<Serology, "serologyClear">): Promise<Serology> {
    return apiRequest<Serology>(`/api/cases/${encodeURIComponent(caseId)}/serology`, { method: "PUT", body: serology })
}

/** Signed-off corneas as recommendation candidates (doctors only: they carry serology status). */
export function listCandidates(): Promise<MatchCandidate[]> {
    return apiRequest<MatchCandidate[]>("/api/cases/candidates")
}

/** A saved run of one module with the case it belongs to. */
export interface ModuleRun {
    run: RunSummary
    caseId: string
    tissueId: string
}

/** One page of a module's saved runs, newest first; nextBefore fetches the older ones. */
export interface ModuleRunPage {
    items: ModuleRun[]
    nextBefore: string | null
}

/** Saved runs of one module across cases (or one case, by tissue ID), newest first. Audited. */
export function listModuleRuns(
    module: RunSummary["module"],
    options: { tissueId?: string; before?: string; limit?: number } = {},
): Promise<ModuleRunPage> {
    const query = new URLSearchParams({ module })
    if (options.tissueId) query.set("tissueId", options.tissueId)
    if (options.before) query.set("before", options.before)
    if (options.limit) query.set("limit", String(options.limit))
    return apiRequest<ModuleRunPage>(`/api/cases/runs?${query}`)
}

export type ImportMode = "create" | "update"

export interface ImportRow {
    row: number
    tissueId: string | null
    /** "create", "update", "skip" or "error". */
    action: "create" | "update" | "skip" | "error"
    errors: string[]
}

export interface ImportReport {
    applied: boolean
    mode: ImportMode
    rows: number
    created: number
    updated: number
    skipped: number
    withErrors: number
    ignoredColumns: string[]
    details: ImportRow[]
}

/** Checks a CSV or .xlsx file and reports what each row would do; changes nothing. */
export function checkCaseImport(file: File, mode: ImportMode): Promise<ImportReport> {
    const form = new FormData()
    form.append("file", file)
    return apiUpload<ImportReport>(`/api/cases/import?mode=${mode}&apply=false`, form)
}

/** Imports the file in one go; refused (422) if any row has an error. */
export function applyCaseImport(file: File, mode: ImportMode): Promise<ImportReport> {
    const form = new FormData()
    form.append("file", file)
    return apiUpload<ImportReport>(`/api/cases/import?mode=${mode}&apply=true`, form)
}

export function downloadImportTemplate(): Promise<Blob> {
    return apiBlob("/api/cases/import/template", "text/csv")
}
