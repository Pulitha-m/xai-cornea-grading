import type { MatchCandidate, SerologyStatus, TissueGrade } from "@/api/recommendation"
import { normaliseStudyId, studyIdError } from "@/lib/study-id"

/** Form helpers for the donor-tissue matching page (kept out of the component file). */
export const GRADES: TissueGrade[] = ["A+", "A", "B", "C"]
export const SEROLOGY: SerologyStatus[] = ["Yes", "Unknown", "No"]
export const SURGERIES = ["PK", "DALK", "DSEK", "DMEK", "Lamellar", "Patch/Tectonic", "Other"]

export interface CandidateRow {
    key: number
    recordId: string
    grade: TissueGrade | ""
    ecd: string
    cv: string
    hex: string
    donorAge: string
    deathToPreservationH: string
    daysInStorage: string
    serologyClear: SerologyStatus
}

export const NUMBER_COLUMNS = [
    { key: "ecd", short: "ECD", label: "ECD (cells/mm²)", hint: "Endothelial cell density; higher is better.", max: 5000 },
    { key: "cv", short: "CV", label: "CV (%)", hint: "Variation in cell size; lower is better.", max: 100 },
    { key: "hex", short: "HEX", label: "HEX (%)", hint: "Share of six-sided cells; higher is better.", max: 100 },
    { key: "donorAge", short: "Donor age", label: "Donor age (years)", hint: "Age of the donor.", max: 100 },
    {
        key: "deathToPreservationH",
        short: "Death to preservation",
        label: "Death → preservation (hours)",
        hint: "Hours from the donor's death until the cornea was placed in preservation medium; shorter is better.",
        max: 72,
    },
    { key: "daysInStorage", short: "Days in storage", label: "Days in storage", hint: "Days since preservation; fresher is better.", max: 60 },
] as const

let nextKey = 1

export function emptyRow(): CandidateRow {
    return {
        key: nextKey++, recordId: "", grade: "", ecd: "", cv: "", hex: "", donorAge: "",
        deathToPreservationH: "", daysInStorage: "", serologyClear: "Unknown",
    }
}

function num(v: string): number | null {
    const t = v.trim()
    if (t === "") return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
}

/**
 * Rows -> candidates. `problems`: rows without an ID or with a value that is not a number;
 * `invalid`: IDs that are not study codes (R + 4 digits), impossible values (outside 0 to the column
 * maximum) and tissue IDs used twice. IDs are sent trimmed and upper-cased.
 */
export function toCandidates(rows: CandidateRow[]): { candidates: MatchCandidate[]; problems: string[]; invalid: string[] } {
    const problems: string[] = []
    const invalid: string[] = []
    const candidates = rows.map((r, i): MatchCandidate => {
        const id = normaliseStudyId(r.recordId)
        const label = id || `row ${i + 1}`
        if (!id) problems.push(`row ${i + 1}: tissue ID`)
        else if (studyIdError("cornea", id)) invalid.push(studyIdError("cornea", id)!)
        const value = (key: (typeof NUMBER_COLUMNS)[number]["key"], name: string) => {
            const n = num(r[key])
            if (r[key].trim() !== "" && n === null) problems.push(`${label}: ${name}`)
            const max = NUMBER_COLUMNS.find((c) => c.key === key)!.max
            if (n !== null && (n < 0 || n > max)) invalid.push(`${label}: ${name} must be between 0 and ${max}`)
            return n
        }
        return {
            recordId: id,
            grade: r.grade || null,
            ecd: value("ecd", "ECD"),
            cv: value("cv", "CV"),
            hex: value("hex", "HEX"),
            donorAge: value("donorAge", "donor age"),
            deathToPreservationH: value("deathToPreservationH", "death-to-preservation time"),
            daysInStorage: value("daysInStorage", "days in storage"),
            serologyClear: r.serologyClear,
        }
    })
    const seen = new Set<string>()
    for (const id of candidates.map((c) => c.recordId).filter(Boolean)) {
        if (seen.has(id) && !invalid.includes(`tissue ID ${id} is used twice`)) invalid.push(`tissue ID ${id} is used twice`)
        seen.add(id)
    }
    return { candidates, problems, invalid }
}
