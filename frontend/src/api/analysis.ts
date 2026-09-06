export interface AnalyzeRequest {
    imageUrl: string
    caseId: string
}

export interface CellularResult {
    status: string
    error: string | null
    cellCount: number | null
    ecd: number | null
    coefficientOfVariation: number | null
    hexagonality: number | null
}

export interface GradingResult {
    status: string
    error: string | null
    grade: string | null
    confidence: number | null
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