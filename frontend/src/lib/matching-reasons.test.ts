import { describe, expect, it } from "vitest"
import type { RankedCandidate } from "@/api/recommendation"
import { rankReason } from "@/lib/matching-reasons"

function cornea(over: Partial<RankedCandidate>): RankedCandidate {
    return {
        rank: 1, recordId: "T1", grade: "A", mlScore: 0, matchScore: 0.8, mcdaRank: 1, gradeGap: 0,
        criterionScores: {}, reasons: [], why: [], whyText: null, counterfactual: null, flags: [], ...over,
    }
}

const WEIGHTS = { grade_fit: 0.35, endothelium: 0.3, serology: 0.2, freshness: 0.1, surgery_compatibility: 0.05 }

describe("rankReason", () => {
    it("splits the ML score gap between #1 and #2 exactly per reason", () => {
        const ranked = [
            cornea({ rank: 1, recordId: "T0001", mlScore: 0.6,
                why: [{ reason: "serology", effect: 0.49 }, { reason: "endothelium", effect: -0.25 }, { reason: "freshness", effect: -0.19 }] }),
            cornea({ rank: 2, recordId: "T003", mlScore: -0.4, flags: ["serology not confirmed"],
                counterfactual: "would be #1 if: serology confirmed clear; or stored 2 fewer days",
                why: [{ reason: "serology", effect: -0.49 }, { reason: "endothelium", effect: 0.06 }, { reason: "freshness", effect: 0.11 }] }),
        ]
        expect(rankReason(ranked, 0, true, WEIGHTS)).toEqual({
            comparedWith: 2, better: ["serology confirmed clear"], worse: ["weaker endothelium", "longer in storage"],
            closeCall: false, serologyNote: null,
        })
        const second = rankReason(ranked, 1, true, WEIGHTS)
        expect(second.worse).toEqual(["serology not yet confirmed"])
        expect(second.better).toEqual(["healthier endothelium", "fresher (fewer days in storage)"])
        expect(second.serologyNote).toBe("Would rank #1 once its serology is confirmed clear.")
    })

    it("uses the weighted MCDA criteria for the MCDA ranking and marks a close call", () => {
        const ranked = [
            cornea({ rank: 1, matchScore: 0.85, criterionScores: { grade_fit: 1, endothelium: 0.8, serology: 1, freshness: 0.5, surgery_compatibility: 1 } }),
            cornea({ rank: 2, recordId: "T2", matchScore: 0.84, criterionScores: { grade_fit: 1, endothelium: 0.85, serology: 1, freshness: 0.6, surgery_compatibility: 1 } }),
        ]
        const r = rankReason(ranked, 1, false, WEIGHTS)
        expect(r.comparedWith).toBe(1)
        expect(r.better).toEqual(["healthier endothelium", "fresher (fewer days in storage)"])
        expect(r.worse).toEqual([])
        expect(r.closeCall).toBe(true)
    })

    it("says when a cornea is the only eligible one and asks to confirm pending serology at #1", () => {
        const r = rankReason([cornea({ flags: ["serology not confirmed"] })], 0, true, WEIGHTS)
        expect(r.comparedWith).toBeNull()
        expect(r.serologyNote).toBe("Confirm the serology is clear before allocating this cornea.")
    })
})
