/**
 * Clinician-facing reading aids for the Grad-CAM maps of the v2 disease model.
 *
 * `lookFor`: the specular microscopy appearance to check inside the highlighted area.
 * `evidence`: how much the image itself carries the finding, from the held-out test AUCs in
 * ml-service/models/disease_v2/summary_final.json (numbers only vs image only).
 * To be reviewed by the clinical supervisor.
 */
export interface GradcamExplanation {
    lookFor: string
    evidence: string
}

export const GRADCAM_EXPLANATIONS: Record<string, GradcamExplanation> = {
    FECD: {
        lookFor:
            "Guttae: dark, round or oval spots in the cell mosaic, sometimes with a small bright centre, which may merge into larger dark areas. Surrounding cells are often enlarged and irregular.",
        evidence:
            "Image and values both matter: low ECD, high CV and low HEX % also raise this score (test AUC numbers only 0.87, image only 0.83).",
    },
    Guttata: {
        lookFor:
            "Isolated dark, round spots (guttae) interrupting the regular mosaic; the cells between them may look normal.",
        evidence:
            "Comes mainly from the image: the CellChek values carry little information for guttata (test AUC numbers only 0.60, image only 0.87).",
    },
    Folds: {
        lookFor:
            "Dark linear or curved bands crossing the image, along which the mosaic is blurred or distorted (folds or striae in Descemet's membrane).",
        evidence:
            "Comes mainly from the image (test AUC numbers only 0.61, image only 0.78).",
    },
    PolyPleo: {
        lookFor:
            "Cells of clearly different sizes (polymegathism) and cells that are not six-sided (pleomorphism).",
        evidence:
            "High CV and low HEX % strongly raise this score (test AUC numbers only 0.86, image only 0.79), so the map shows only part of the reason.",
    },
    LowCD: {
        lookFor: "Fewer, larger cells across the field than in a healthy endothelium.",
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
