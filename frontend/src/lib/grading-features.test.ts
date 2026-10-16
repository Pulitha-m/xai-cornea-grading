import { describe, expect, it } from "vitest"
import { buildFeaturePayload, emptyFeatureInputs, FEATURES } from "@/lib/grading-features"

// The schema exported from the training code (ml-service/models/grading_feature_schema.json).
const schemas = import.meta.glob("../../../ml-service/models/grading_feature_schema.json", { eager: true, import: "default" })
const schema = Object.values(schemas)[0] as {
    order: string[]
    features: { name: string; type: string; allowed?: (string | number)[] }[]
} | undefined

describe("grading features", () => {
    it.skipIf(!schema)("match the training schema: order, types and categories", () => {
        expect(FEATURES.map((f) => f.name)).toEqual(schema!.order)
        for (const spec of schema!.features) {
            const feature = FEATURES.find((f) => f.name === spec.name)!
            expect(feature.type).toBe(spec.type)
            if (spec.type === "category") {
                expect(feature.options).toEqual(spec.allowed)
            }
        }
    })

    it("sends every feature, with null for not recorded", () => {
        const { payload, errors } = buildFeaturePayload(emptyFeatureInputs())
        expect(Object.keys(payload)).toHaveLength(24)
        expect(Object.values(payload).every((v) => v === null)).toBe(true)
        expect(errors).toEqual({})
    })

    it("converts values and keeps zero distinct from not recorded", () => {
        const inputs = { ...emptyFeatureInputs(), ECD_CD_cells_per_mm2: "2600", Stroma_Has_Scar: "0", Descemet_Fold_Severity: "Mild" }
        const { payload } = buildFeaturePayload(inputs)
        expect(payload.ECD_CD_cells_per_mm2).toBe(2600)
        expect(payload.Stroma_Has_Scar).toBe(0)
        expect(payload.Descemet_Fold_Severity).toBe("Mild")
    })

    it("reports malformed and impossible values", () => {
        const inputs = { ...emptyFeatureInputs(), CV: "abc", HEX_percent: "120", Total_Cell_Count: "10.5", SD: "-3" }
        expect(Object.keys(buildFeaturePayload(inputs).errors).sort()).toEqual(["CV", "HEX_percent", "SD", "Total_Cell_Count"])
    })
})
