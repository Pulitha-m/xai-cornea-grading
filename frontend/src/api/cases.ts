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
    createdAt: string
    updatedAt: string
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
