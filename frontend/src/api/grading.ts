import type { EcdReference, FeatureWarning, ImageValidation } from "@/api/analysis"
import { apiRequest } from "@/lib/api-client"

export interface GradingAnalyzeRequest {
    caseId: string
    /** Id returned by uploadImage (POST /api/analysis/images). */
    imageId: string
    /** All 24 grading features (see lib/grading-features); null = not recorded. */
    clinicalFeatures: Record<string, number | string | null>
}

export interface FeatureContribution {
    name: string
    /** As given to the model; null = not recorded. */
    value: number | string | null
    /** SHAP value: change in the explained grade's share of tree votes. */
    contribution: number
}

export interface ImageAttributionMap {
    method: string
    /** Base64 PNGs of the regions that raised / lowered the grade's share of votes, each scaled to its own maximum. */
    supportingPng: string | null
    opposingPng: string | null
    supportingTotal: number
    opposingTotal: number
    /** Share of the image's attribution that the maps localise. */
    localisedShare: number
}

/** TreeSHAP: baseline + all feature contributions + imageContribution = prediction. Explains the model, not the cornea. */
export interface GradingExplanation {
    method: string
    explainedGrade: string
    /** Training average share of trees voting for the explained grade. */
    baseline: number
    prediction: number
    /** The 24 inputs, largest |contribution| first. */
    features: FeatureContribution[]
    imageContribution: number
    imageMap: ImageAttributionMap | null
    message: string
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
    /** Null if the explanation could not be computed; the grade is still valid. */
    explanation: GradingExplanation | null
}

export function analyzeGrading(request: GradingAnalyzeRequest): Promise<GradingAnalyzeResponse> {
    return apiRequest<GradingAnalyzeResponse>("/api/analysis/grading", { method: "POST", body: request })
}
