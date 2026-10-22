/**
 * Clinician-facing reading aids for the Grad-CAM maps of the v2 disease model.
 *
 * `lookFor`: short points on the specular microscopy appearance to check inside the highlighted area.
 * `evidence`: how much the image itself carries the finding, from the held-out test AUCs in
 * ml-service/models/disease_v2/summary_final.json (numbers only vs image only). Not shown in the UI.
 * To be reviewed by the clinical supervisor.
 */
export interface GradcamExplanation {
    lookFor: string[]
    evidence: string
}

export const GRADCAM_EXPLANATIONS: Record<string, GradcamExplanation> = {
    FECD: {
        lookFor: [
            "Guttae: dark, round or oval spots, sometimes with a small bright centre",
            "Spots that merge into larger dark areas",
            "Enlarged, irregular cells around them",
        ],
        evidence:
            "Image and values both matter: low ECD, high CV and low HEX % also raise this score (test AUC numbers only 0.87, image only 0.83).",
    },
    Guttata: {
        lookFor: [
            "Isolated dark, round spots (guttae) interrupting the mosaic",
            "Cells between the spots may look normal",
        ],
        evidence:
            "Comes mainly from the image: the CellChek values carry little information for guttata (test AUC numbers only 0.60, image only 0.87).",
    },
    Folds: {
        lookFor: [
            "Dark linear or curved bands crossing the image",
            "Blurred or distorted mosaic along the bands (folds or striae in Descemet's membrane)",
        ],
        evidence:
            "Comes mainly from the image (test AUC numbers only 0.61, image only 0.78).",
    },
    PolyPleo: {
        lookFor: [
            "Cells of clearly different sizes (polymegathism)",
            "Cells that are not six-sided (pleomorphism)",
        ],
        evidence:
            "High CV and low HEX % strongly raise this score (test AUC numbers only 0.86, image only 0.79), so the map shows only part of the reason.",
    },
    LowCD: {
        lookFor: [
            "Fewer cells across the field than in a healthy endothelium",
            "Cells larger than normal",
        ],
        evidence:
            "Driven largely by the ECD value (test AUC numbers only 0.98, image only 0.93); the map shows only the image's contribution.",
    },
}

/** "focused" / "moderate" / "widespread" from the share of the image highlighted. */
export function coverageLabel(coverage: number): string {
    if (coverage < 0.15) return "focused"
    if (coverage < 0.4) return "moderate"
    return "widespread"
}

/**
 * Cell of the 3 x 3 grid named by the server's focus region ("upper left", "right", "centre", ...),
 * or null for an unknown name.
 */
export function regionCell(region: string): { row: number; col: number } | null {
    const words = region.split(" ")
    if (words.some((w) => !["upper", "lower", "left", "right", "centre"].includes(w))) return null
    const row = words.includes("upper") ? 0 : words.includes("lower") ? 2 : 1
    const col = words.includes("left") ? 0 : words.includes("right") ? 2 : 1
    return { row, col }
}
