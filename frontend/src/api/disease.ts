import type { ImageValidation } from "@/api/analysis"
import { apiRequest } from "@/lib/api-client"

export interface DiseaseAnalyzeRequest {
    caseId: string
    /** Id returned by uploadImage (POST /api/analysis/images). */
    imageId: string
    /** The five CellChek values by name (see lib/disease-measurements); null = not recorded, never 0. */
    measurements: Record<string, number | null>
    /** Run the models even if the input checks fail; the result is then marked as not reliable. */
    force: boolean
}

export interface InputIssue {
    code: string
    /** A measurement name, "image", or null for the whole request. */
    field: string | null
    message: string
}

export interface InputCheck {
    passed: boolean
    /** The checks failed and the analysis was forced. */
    forced: boolean
    errors: InputIssue[]
    warnings: InputIssue[]
}

export interface ImageQuality {
    /** "OK", "Low" or "Unusable". */
    rating: string
    focus: number
    focusLowLimit: number
    darkFraction: number
    saturatedFraction: number
    contrast: number
    /** Distance to the training images (0 = identical); warn/reject limits alongside. */
    unusualDistance: number
    unusualWarnAbove: number
    unusualRejectAbove: number
}

export interface DiseaseFinding {
    code: string
    label: string
    /** Model output; not calibrated, not a confidence. */
    probability: number
    threshold: number
    detected: boolean
    /** Base64 PNG of the Grad-CAM over the input image, for detected diseases. */
    gradcamPng: string | null
    /** Where the map is hottest and the share of the image it highlights, for detected diseases. */
    gradcamFocus: GradcamFocus | null
}

export interface GradcamFocus {
    /** "centre", "upper", "lower", "left", "right" or a corner such as "lower right". */
    region: string
    /** Share of the image at or above half the map's maximum (0–1). */
    coverage: number
}

export interface SeverityFinding {
    group: string
    label: string
    diseases: string[]
    /** "Mild" or "Mod/Sev". */
    grade: string
    probability: number | null
    threshold: number | null
    method: string
}

export interface DiseaseAnalyzeResponse {
    analysisId: string | null
    caseId: string
    /** "completed", or "input_check_failed" (then only inputCheck and imageQuality are set). */
    status: string
    message: string | null
    imageValidation: ImageValidation | null
    inputCheck: InputCheck | null
    imageQuality: ImageQuality | null
    method: string | null
    diseases: DiseaseFinding[] | null
    detected: string[] | null
    normal: boolean | null
    severity: SeverityFinding[] | null
    /** "None", "Mild" or "Mod/Sev". */
    overallSeverity: string | null
    severityProbabilities: Record<string, number> | null
    measurementsUsed: Record<string, number | null> | null
    measurementsNotRecorded: string[] | null
    reliable: boolean | null
}

export function analyzeDisease(request: DiseaseAnalyzeRequest): Promise<DiseaseAnalyzeResponse> {
    return apiRequest<DiseaseAnalyzeResponse>("/api/analysis/disease", { method: "POST", body: request })
}
