import type { ImageValidation } from "@/api/analysis"
import { apiRequest } from "@/lib/api-client"

export interface CellularAnalyzeRequest {
    caseId: string
    /** Id returned by uploadImage (POST /api/analysis/images). */
    imageId: string
}

/** Over all complete cells, at the calibrated scale. CV, hexagonality and cvCompactness are percentages (not fractions). */
export interface CellularBiomarkers {
    cellCount: number
    /** cells/mm² */
    ecd: number | null
    meanAreaUm2: number | null
    sdAreaUm2: number | null
    coefficientOfVariation: number | null
    hexagonality: number | null
    /** Cells fully surrounded by other cells; HEX is computed over these. */
    cellsWithSides: number
    meanCompactness: number | null
    sdCompactness: number | null
    cvCompactness: number | null
    /** p5, p25, p50, p75, p95 in µm². */
    areaPercentilesUm2: Record<string, number | null>
    /** Share of cells with "<=4", "5", "6", "7", ">=8" sides, %. */
    sideDistributionPct: Record<string, number | null>
    /** Implausibly small or large cells (kept in the biomarkers). */
    flaggedCells: number
}

export interface CellularRoi {
    method: string
    shareOfImage: number
    /** Share of the illuminated area judged analysable (0..1). */
    shareOfLitArea: number
    /** Mean P(analysable) over the illuminated area (0..1). */
    qualityScore: number
}

export interface QualityFlag {
    /** "error": the biomarkers are not reliable; "warning": check. */
    level: string
    code: string
    message: string
}

/** 95 % CIs [low, high]: sampling only, not segmentation error. */
export interface CellularUncertainty {
    method: string
    ecdCi95: (number | null)[]
    cvCi95: (number | null)[]
    hexCi95: (number | null)[]
}

export interface CellularEvidence {
    mostExtremeCellsPct: number
    theirShareOfAreaVariancePct: number | null
}

export interface CellularReliability {
    rule: string
    green: number
    yellow: number
    red: number
    medianConfidence: number | null
}

/** Base64 JPEG overlays of the analysed image. */
export interface CellularImages {
    overlayJpeg: string
    reliabilityJpeg: string | null
    cvEvidenceJpeg: string
}

export interface CellularAnalyzeResponse {
    analysisId: string | null
    caseId: string
    status: string
    message: string | null
    imageValidation: ImageValidation | null
    method: string | null
    /** µm per pixel (calibrated). */
    umPerPx: number | null
    /** false if the image size differs from the validated 1296 × 972. */
    validatedImageSize: boolean | null
    biomarkers: CellularBiomarkers
    roi: CellularRoi | null
    qualityFlags: QualityFlag[]
    /** false if a quality flag of level "error" was raised. */
    reliable: boolean | null
    uncertainty: CellularUncertainty | null
    evidence: CellularEvidence | null
    reliability: CellularReliability | null
    images: CellularImages | null
    seconds: number | null
}

export function analyzeCellular(request: CellularAnalyzeRequest): Promise<CellularAnalyzeResponse> {
    return apiRequest<CellularAnalyzeResponse>("/api/analysis/cellular", { method: "POST", body: request })
}
