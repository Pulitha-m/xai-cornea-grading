import { ECD_MAX_INCLUSIVE, ECD_MIN_EXCLUSIVE } from "@/api/analysis"

/** Parses the optional ECD field. Blank means "not available". */
export function parseEcd(value: string): { ecd: number | null; error: string | null } {
    const trimmed = value.trim()
    if (trimmed === "") {
        return { ecd: null, error: null }
    }
    const ecd = Number(trimmed)
    if (!Number.isFinite(ecd) || ecd <= ECD_MIN_EXCLUSIVE || ecd > ECD_MAX_INCLUSIVE) {
        return {
            ecd: null,
            error: `ECD must be a number greater than ${ECD_MIN_EXCLUSIVE} and at most ${ECD_MAX_INCLUSIVE} cells/mm².`,
        }
    }
    return { ecd, error: null }
}
