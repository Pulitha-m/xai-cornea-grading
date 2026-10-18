/**
 * The five CellChek inputs of the v2 disease model, by their training-data names. The server
 * checks possible ranges, SD consistency and missing values (ml-service pipelines/disease/checks.py).
 */
export interface MeasurementDef {
    name: string
    label: string
    unit?: string
}

export const MEASUREMENTS: MeasurementDef[] = [
    { name: "ECD_CD_cells_per_mm2", label: "ECD", unit: "cells/mm²" },
    { name: "SD", label: "SD of cell area", unit: "µm²" },
    { name: "CV", label: "Coefficient of variation", unit: "%" },
    { name: "HEX_percent", label: "Hexagonality", unit: "%" },
    { name: "Donor_Age", label: "Donor age", unit: "years" },
]

export type MeasurementInputs = Record<string, string>

export function emptyMeasurementInputs(): MeasurementInputs {
    return Object.fromEntries(MEASUREMENTS.map((m) => [m.name, ""]))
}

export function measurementLabel(name: string): string {
    return MEASUREMENTS.find((m) => m.name === name)?.label ?? name
}

/**
 * Form inputs to the API payload: blank = null (not recorded, never 0). Only malformed numbers are
 * caught here; impossible values go to the server so its checks explain them and the user may force.
 */
export function buildMeasurementPayload(inputs: MeasurementInputs): {
    payload: Record<string, number | null>
    errors: Record<string, string>
} {
    const payload: Record<string, number | null> = {}
    const errors: Record<string, string> = {}
    for (const m of MEASUREMENTS) {
        const raw = (inputs[m.name] ?? "").trim()
        if (raw === "") {
            payload[m.name] = null
            continue
        }
        const value = Number(raw)
        if (!Number.isFinite(value)) {
            errors[m.name] = `${m.label} must be a number, or blank if unknown.`
            payload[m.name] = null
        } else {
            payload[m.name] = value
        }
    }
    return { payload, errors }
}
