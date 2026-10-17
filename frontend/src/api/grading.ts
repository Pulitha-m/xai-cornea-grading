import type { EcdReference, FeatureWarning, ImageValidation } from "@/api/analysis"
import { apiRequest } from "@/lib/api-client"

export interface GradingAnalyzeRequest {
    caseId: string
    /** Id returned by uploadImage (POST /api/analysis/images). */
    imageId: string
    /** All 24 grading features (see lib/grading-features); null = not recorded. */
    clinicalFeatures: Record<string, number | string | null>
}

export interface GradingAnalyzeResponse {
    analysisId: string | null
    caseId: string
    /** "completed"; failures are returned as errors, never as a result without a grade. */
    status: string
    imageValidation: ImageValidation | null
    grade: string
    method: string
    /** Share of trees voting for each grade. Not calibrated; not a confidence. */
    modelProbabilities: Record<string, number>
    /** The validated 24 features as given to the model; null = not recorded. */
    featuresUsed: Record<string, number | string | null>
    featuresNotRecorded: string[]
    warnings: FeatureWarning[]
    ecdReference: EcdReference
    reviewRequired: boolean
    message: string
}

export function analyzeGrading(request: GradingAnalyzeRequest): Promise<GradingAnalyzeResponse> {
    return apiRequest<GradingAnalyzeResponse>("/api/analysis/grading", { method: "POST", body: request })
}
