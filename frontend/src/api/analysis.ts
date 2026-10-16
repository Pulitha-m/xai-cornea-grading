/** Valid ECD range accepted by ml-service (cells/mm²): ECD_MIN_EXCLUSIVE < ecd <= ECD_MAX_INCLUSIVE. */
export const ECD_MIN_EXCLUSIVE = 0
export const ECD_MAX_INCLUSIVE = 6000

export interface AnalyzeRequest {
    imageUrl: string
    caseId: string
    /** Endothelial cell density (cells/mm²) from the specular microscopy report. */
    ecd?: number | null
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

export interface GradingResult {
    /** "completed", "review_required" (no ECD supplied) or "failed". */
    status: string
    error: string | null
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
    caseId: string
    status: string
    cellular: CellularResult
    grading: GradingResult
    disease: DiseaseResult
    recommendation: RecommendationResult
}

const API_BASE_URL = "http://localhost:8080"

export async function analyzeCornea(
    request: AnalyzeRequest,
): Promise<AnalyzeResponse> {
    const response = await fetch(`${API_BASE_URL}/api/analysis`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
    })

    if (!response.ok) {
        throw new Error(`Analysis request failed: ${response.status}`)
    }

    return response.json()
}