import { apiRequest, apiUpload } from "@/lib/api-client"

/** Upload limits; the server enforces the same limits (app.analysis.images / ml-service IMAGE_*). */
export const IMAGE_MAX_BYTES = 15 * 1024 * 1024
export const IMAGE_MIN_SIDE = 224
export const IMAGE_MAX_SIDE = 8000
export const IMAGE_ACCEPT = "image/jpeg,image/png"

export interface ImageUploadResponse {
    imageId: string
    caseId: string
    contentType: string
    sizeBytes: number
    width: number
    height: number
}

export interface AnalyzeRequest {
    caseId: string
    /** Id returned by uploadImage; images are never referenced by URL. */
    imageId: string
    /** All 24 grading features (see lib/grading-features); null = not recorded. */
    clinicalFeatures: Record<string, number | string | null>
}

export interface ImageValidation {
    /** "VALID_CORNEAL_IMAGE", or "UNVALIDATED_DEV_MODE" when the development bypass is on. */
    domainStatus: string
    /** Image quality and cell detail are not assessed by this version. */
    qualityAssessed: boolean
    width: number
    height: number
    format: string
}

export interface CellularResult {
    status: string
    error: string | null
    cellCount: number | null
    ecd: number | null
    coefficientOfVariation: number | null
    hexagonality: number | null
}

export interface EcdBand {
    lowerExclusive: number | null
    upperInclusive: number | null
}

/** Reference grade from the ECD threshold tree (single-feature baseline). */
export interface EcdReference {
    /** "completed", or "review_required" when ECD was not recorded or is out of range. */
    status: string
    grade: string | null
    method: string | null
    ecdUsed: number | null
    ecdBand: EcdBand | null
    /** Recorded grades of training tissues in the same ECD band; not model confidence. */
    bandDistribution: Record<string, number> | null
    bandTrainingTissues: number | null
    reviewRequired: boolean | null
    message: string | null
}

export interface FeatureWarning {
    code: string
    field: string | null
    message: string
}

export interface GradingResult {
    /** "completed" or "failed". */
    status: string
    error: string | null
    grade: string | null
    method: string | null
    /** Share of trees voting for each grade. Not calibrated; not a confidence. */
    modelProbabilities: Record<string, number> | null
    featuresNotRecorded: string[] | null
    warnings: FeatureWarning[] | null
    ecdReference: EcdReference | null
    reviewRequired: boolean | null
    message: string | null
}

export interface DiseaseResult {
    status: string
    error: string | null
    disease: string | null
    severity: string | null
    confidence: number | null
}

export interface RecommendationResult {
    status: string
    error: string | null
    recommendation: string | null
    confidence: number | null
}

export interface AnalyzeResponse {
    analysisId: string | null
    caseId: string
    /** "completed" when every module completed, otherwise "partial". */
    status: string
    imageValidation: ImageValidation | null
    cellular: CellularResult
    grading: GradingResult
    disease: DiseaseResult
    recommendation: RecommendationResult
}

export function uploadImage(
    caseId: string,
    file: File,
    onProgress?: (fraction: number) => void,
): Promise<ImageUploadResponse> {
    const form = new FormData()
    form.append("caseId", caseId)
    form.append("file", file)
    return apiUpload<ImageUploadResponse>("/api/analysis/images", form, { onProgress })
}

export function analyzeCornea(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    return apiRequest<AnalyzeResponse>("/api/analysis", { method: "POST", body: request })
}
