/**
 * The 24 clinical inputs of the hybrid grading model, in training order. Mirrors
 * ml-service/models/grading_feature_schema.json (checked by grading-features.test.ts);
 * the server validates every request against that schema.
 */
export type FeatureType = "number" | "binary" | "category"

export interface FeatureDef {
    name: string
    label: string
    group: "konan" | "stroma" | "epithelium" | "endothelium" | "descemet"
    type: FeatureType
    unit?: string
    integer?: boolean
    max?: number
    options?: string[]
}

export const FEATURE_GROUPS: { id: FeatureDef["group"]; title: string }[] = [
    { id: "konan", title: "Specular microscopy report (Konan)" },
    { id: "stroma", title: "Slit-lamp: stroma" },
    { id: "epithelium", title: "Slit-lamp: epithelium" },
    { id: "endothelium", title: "Slit-lamp: endothelium" },
    { id: "descemet", title: "Slit-lamp: Descemet's membrane" },
]

export const FEATURES: FeatureDef[] = [
    { name: "ECD_CD_cells_per_mm2", label: "ECD", group: "konan", type: "number", unit: "cells/mm²" },
    { name: "CV", label: "Coefficient of variation", group: "konan", type: "number", unit: "%" },
    { name: "HEX_percent", label: "Hexagonality", group: "konan", type: "number", unit: "%", max: 100 },
    { name: "SD", label: "SD of cell area", group: "konan", type: "number", unit: "µm²" },
    { name: "Total_Cell_Count", label: "Cells analysed", group: "konan", type: "number", unit: "cells", integer: true },
    { name: "Total_Area_um2", label: "Total area analysed", group: "konan", type: "number", unit: "µm²" },
    { name: "Stroma_Is_Clear", label: "Clear", group: "stroma", type: "binary" },
    { name: "Stroma_Is_Compact", label: "Compact", group: "stroma", type: "binary" },
    { name: "Stroma_Has_Arcus", label: "Arcus", group: "stroma", type: "binary" },
    { name: "Stroma_Has_Edema", label: "Oedema", group: "stroma", type: "binary" },
    { name: "Stroma_Has_Scar", label: "Scar", group: "stroma", type: "binary" },
    { name: "Epi_Has_Arcus", label: "Arcus", group: "epithelium", type: "binary" },
    { name: "Epi_Has_Defect", label: "Defect", group: "epithelium", type: "binary" },
    { name: "Epi_Has_Exposure", label: "Exposure", group: "epithelium", type: "binary" },
    { name: "Epi_Has_Haze", label: "Haze", group: "epithelium", type: "binary" },
    { name: "Endo_Has_Stress_Lines", label: "Stress lines", group: "endothelium", type: "binary" },
    { name: "Endo_Has_RBC", label: "Red blood cells", group: "endothelium", type: "binary" },
    { name: "Endo_Has_Cell_Dropout", label: "Cell dropout", group: "endothelium", type: "binary" },
    { name: "Descemet_Has_Folds", label: "Folds", group: "descemet", type: "binary" },
    { name: "Descemet_Fold_Severity", label: "Fold severity", group: "descemet", type: "category", options: ["Mild", "Moderate", "Unspecified", "Very mild"] },
    { name: "Descemet_Fold_Relative_Number", label: "Number of folds", group: "descemet", type: "category", options: ["Mild", "Moderate", "Several", "Several/Moderate", "Unspecified"] },
    { name: "Endo_Stress_Line_Location", label: "Stress line location", group: "endothelium", type: "category", options: ["Central", "Central + Peripheral", "Peripheral", "Unspecified"] },
    { name: "Stroma_Arcus_Severity", label: "Arcus severity", group: "stroma", type: "category", options: ["Mild", "Moderate", "Unspecified"] },
    { name: "Epi_Exposure_Severity", label: "Exposure severity", group: "epithelium", type: "category", options: ["Mild", "Unspecified", "Very mild"] },
]

export function featureLabel(name: string): string {
    const feature = FEATURES.find((f) => f.name === name)
    if (!feature) return name
    const group = FEATURE_GROUPS.find((g) => g.id === feature.group)!
    if (feature.group === "konan") return feature.label
    const area = group.title.replace("Slit-lamp: ", "")
    return `${area.charAt(0).toUpperCase()}${area.slice(1)}: ${feature.label}`
}

export type FeatureInputs = Record<string, string>

export function emptyFeatureInputs(): FeatureInputs {
    return Object.fromEntries(FEATURES.map((f) => [f.name, ""]))
}

/**
 * Converts form inputs to the API payload (all 24 keys; null = not recorded) and reports
 * malformed values. Immediate feedback only: the server validates against the training schema.
 */
export function buildFeaturePayload(inputs: FeatureInputs): {
    payload: Record<string, number | string | null>
    errors: Record<string, string>
} {
    const payload: Record<string, number | string | null> = {}
    const errors: Record<string, string> = {}

    for (const feature of FEATURES) {
        const raw = (inputs[feature.name] ?? "").trim()
        if (raw === "") {
            payload[feature.name] = null
            continue
        }
        if (feature.type === "number") {
            const value = Number(raw)
            if (!Number.isFinite(value)) {
                errors[feature.name] = `${feature.label} must be a number.`
            } else if (value <= 0 || (feature.max !== undefined && value > feature.max)) {
                errors[feature.name] = feature.max !== undefined
                    ? `${feature.label} must be greater than 0 and at most ${feature.max} ${feature.unit}.`
                    : `${feature.label} must be greater than 0.`
            } else if (feature.integer && !Number.isInteger(value)) {
                errors[feature.name] = `${feature.label} must be a whole number.`
            }
            payload[feature.name] = errors[feature.name] ? null : value
        } else if (feature.type === "binary") {
            payload[feature.name] = raw === "1" ? 1 : 0
        } else {
            payload[feature.name] = raw
        }
    }
    return { payload, errors }
}
