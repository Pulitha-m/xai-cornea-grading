import type { MatchCandidate, SerologyStatus, TissueGrade } from "@/api/recommendation"

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
    { key: "ecd", short: "ECD", label: "ECD (cells/mm²)", hint: "Endothelial cell density; higher is better." },
    { key: "cv", short: "CV", label: "CV (%)", hint: "Variation in cell size; lower is better." },
    { key: "hex", short: "HEX", label: "HEX (%)", hint: "Share of six-sided cells; higher is better." },
    { key: "donorAge", short: "Donor age", label: "Donor age (years)", hint: "Age of the donor." },
    {
        key: "deathToPreservationH",
        short: "Death to preservation",
        label: "Death → preservation (hours)",
        hint: "Hours from the donor's death until the cornea was placed in preservation medium; shorter is better.",
    },
    { key: "daysInStorage", short: "Days in storage", label: "Days in storage", hint: "Days since preservation; fresher is better." },
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

/** Rows -> candidates; lists rows without an ID or with a value that is not a number. */
export function toCandidates(rows: CandidateRow[]): { candidates: MatchCandidate[]; problems: string[] } {
    const problems: string[] = []
    const candidates = rows.map((r, i): MatchCandidate => {
        const label = r.recordId.trim() || `row ${i + 1}`
        if (!r.recordId.trim()) problems.push(`row ${i + 1}: tissue ID`)
        const value = (key: (typeof NUMBER_COLUMNS)[number]["key"], name: string) => {
            const n = num(r[key])
            if (r[key].trim() !== "" && n === null) problems.push(`${label}: ${name}`)
            return n
        }
        return {
            recordId: r.recordId.trim(),
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
    return { candidates, problems }
}
