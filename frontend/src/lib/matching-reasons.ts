import type { RankedCandidate } from "@/api/recommendation"

/**
 * Plain-language reason for each position in a matching result. Both rankers are white-box, so the
 * difference between two corneas splits exactly into one part per reason:
 *   ML ranker: effect(a) - effect(b) per reason (logistic weight x difference in value; the pool average cancels)
 *   MCDA:      weight x (criterion score(a) - criterion score(b))
 * Each cornea is compared with the one directly above it (#1 with #2).
 */

/** What a reason means for the cornea it describes: [when it helps, when it holds it back]. */
const PHRASES: Record<string, [string, string]> = {
    "grade match": ["closer to the requested grade", "further from the requested grade"],
    grade_fit: ["closer to the requested grade", "further from the requested grade"],
    endothelium: ["healthier endothelium", "weaker endothelium"],
    freshness: ["fresher (fewer days in storage)", "longer in storage"],
    "donor age": ["younger donor", "older donor"],
    "preservation time": ["shorter death-to-preservation time", "longer death-to-preservation time"],
    serology: ["serology confirmed clear", "serology not yet confirmed"],
    surgery_compatibility: ["better fit for the surgery", "poorer fit for the surgery"],
}

// Smallest part that counts as a reason, and the overall gap below which the order is a close call
// (ML: logistic score units; MCDA: share of the 0-1 total). Display thresholds only.
const MIN_PART = { ml: 0.05, mcda: 0.005 }
const CLOSE_GAP = { ml: 0.25, mcda: 0.02 }

export const SEROLOGY_PENDING = "serology not confirmed"

export interface RankReason {
    /** Rank of the cornea it is compared with; null when it is the only eligible cornea. */
    comparedWith: number | null
    /** Reasons this cornea is ahead of (or better than) the compared cornea, strongest first. */
    better: string[]
    /** Reasons it is behind (or weaker than) the compared cornea, strongest first. */
    worse: string[]
    /** The two are close; small changes could swap them. */
    closeCall: boolean
    /** Serology still pending: "must confirm" for #1, "would be #1 once confirmed" otherwise. */
    serologyNote: string | null
}

function phrase(reason: string, helps: boolean): string {
    const p = PHRASES[reason]
    return p ? p[helps ? 0 : 1] : `${helps ? "better" : "weaker"} ${reason.replaceAll("_", " ")}`
}

/** Exact split of score(a) - score(b) into one part per reason. */
function parts(a: RankedCandidate, b: RankedCandidate, ml: boolean, weights: Record<string, number>): Record<string, number> {
    const out: Record<string, number> = {}
    if (ml) {
        for (const w of a.why) out[w.reason] = (out[w.reason] ?? 0) + w.effect
        for (const w of b.why) out[w.reason] = (out[w.reason] ?? 0) - w.effect
    } else {
        for (const [k, weight] of Object.entries(weights)) {
            if (weight > 0) out[k] = weight * ((a.criterionScores[k] ?? 0) - (b.criterionScores[k] ?? 0))
        }
    }
    return out
}

export function rankReason(ranked: RankedCandidate[], index: number, methodMl: boolean, weights: Record<string, number>): RankReason {
    const c = ranked[index]
    const pending = c.flags.includes(SEROLOGY_PENDING)
    const serologyNote = !pending ? null
        : c.rank === 1 ? "Confirm the serology is clear before allocating this cornea."
        : c.counterfactual?.includes("serology confirmed clear") ? "Would rank #1 once its serology is confirmed clear."
        : null

    const other = c.rank === 1 ? ranked[index + 1] : ranked[index - 1]
    if (!other) return { comparedWith: null, better: [], worse: [], closeCall: false, serologyNote }

    // The ML split needs the ML reasons of both corneas; otherwise fall back to the MCDA criteria.
    const ml = methodMl && c.why.length > 0 && other.why.length > 0
    const kind = ml ? "ml" : "mcda"
    const split = Object.entries(parts(c, other, ml, weights)).filter(([, v]) => Math.abs(v) >= MIN_PART[kind])
    const better = split.filter(([, v]) => v > 0).sort((x, y) => y[1] - x[1]).map(([k]) => phrase(k, true))
    const worse = split.filter(([, v]) => v < 0).sort((x, y) => x[1] - y[1]).map(([k]) => phrase(k, false))

    const gap = ml ? Math.abs((c.mlScore ?? 0) - (other.mlScore ?? 0)) : Math.abs(c.matchScore - other.matchScore)
    return { comparedWith: other.rank, better, worse, closeCall: gap < CLOSE_GAP[kind], serologyNote }
}
