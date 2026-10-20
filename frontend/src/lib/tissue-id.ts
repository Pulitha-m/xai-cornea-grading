/**
 * Tissue IDs as users enter them: the last five digits of the tissue number and the eye side,
 * e.g. 12656R or 12656L. Mirrors the backend's TissueNumber, which validates again.
 */
const TISSUE_ID = /^[0-9]{5}[RL]$/

export const TISSUE_ID_PLACEHOLDER = "12656R"
export const TISSUE_ID_HELP = "Five digits followed by R or L, e.g. 12656R."

export function normaliseTissueId(raw: string): string {
    return raw.trim().toUpperCase()
}

/** Null when valid, otherwise a message for the field. */
export function tissueIdError(raw: string): string | null {
    const value = normaliseTissueId(raw)
    if (value === "") return "Enter the tissue ID."
    return TISSUE_ID.test(value) ? null : `Enter the tissue ID as five digits followed by R or L, for example ${TISSUE_ID_PLACEHOLDER}.`
}
