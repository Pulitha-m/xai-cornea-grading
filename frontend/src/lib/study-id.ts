/**
 * Study codes typed into the recommendation forms: request Q0012, cornea R0012, graft G0012 (letter + 4 digits).
 * Real NEBSL tissue IDs (e.g. 12656R) are refused: they stay encrypted in the donor cases and must not be
 * sent to the ML service or stored with the runs. Mirrors the backend's patterns, which check again.
 */
const FORMATS = {
    request: { prefix: "Q", label: "Request ID" },
    cornea: { prefix: "R", label: "Tissue ID" },
    graft: { prefix: "G", label: "Graft ID" },
} as const

export type StudyIdKind = keyof typeof FORMATS

const REAL_TISSUE_ID = /^[0-9]{5}[RL]$/

export function studyIdPlaceholder(kind: StudyIdKind): string {
    return `${FORMATS[kind].prefix}0001`
}

export function normaliseStudyId(raw: string): string {
    return raw.trim().toUpperCase()
}

/** Null when the (non-empty) value is a valid study code, otherwise the reason. */
export function studyIdError(kind: StudyIdKind, raw: string): string | null {
    const value = normaliseStudyId(raw)
    const { prefix, label } = FORMATS[kind]
    if (new RegExp(`^${prefix}[0-9]{4}$`).test(value)) return null
    if (REAL_TISSUE_ID.test(value)) {
        return `${value} looks like a real NEBSL tissue ID; enter the study code instead (${prefix} + 4 digits, e.g. ${prefix}0012)`
    }
    return `${label} ${value} must be ${prefix} followed by 4 digits, e.g. ${prefix}0012`
}
