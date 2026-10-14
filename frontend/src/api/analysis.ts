import { apiRequest } from "@/lib/api-client"

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

export function analyzeCornea(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    return apiRequest<AnalyzeResponse>("/api/analysis", { method: "POST", body: request })
}
