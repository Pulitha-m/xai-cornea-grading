import { describe, expect, it } from "vitest"
import { trajectorySummary } from "@/lib/trajectory-summary"

const p = (months: number, ecd: number, low: number, high: number) => ({ months, ecd, low, high })

describe("trajectorySummary", () => {
    it("healthy graft whose 60-month range dips below 1000 (G0001)", () => {
        expect(trajectorySummary(2300, [p(24, 1977, 1770, 2339), p(36, 1787, 1401, 2168), p(60, 1405, 915, 1859)])).toEqual({
            tone: "warning",
            text: "Predicted to stay above 1000 cells/mm² through month 60 (5 years): 1405. The likely range at month 60 (5 years) (915–1859) dips below 1000.",
        })
    })

    it("healthy graft with the whole range above 1000", () => {
        expect(trajectorySummary(3100, [p(24, 2502, 2300, 2700), p(36, 2172, 1900, 2400), p(60, 1617, 1053, 2100)])).toEqual({
            tone: "success", text: "Predicted to stay above 1000 cells/mm² through month 60 (5 years): 1617.",
        })
    })

    it("falls below 1000 and the range could reach failure (G0002)", () => {
        expect(trajectorySummary(1550, [p(24, 1186, 1062, 1403), p(36, 852, 668, 1034), p(60, 689, 449, 912)])).toEqual({
            tone: "danger",
            text: "Predicted to fall below 1000 cells/mm² by month 36 (3 years): 852. The likely range at month 60 (5 years) (449–912) could reach the 500 failure level.",
        })
    })

    it("falls below 1000 with the range above 500", () => {
        expect(trajectorySummary(1600, [p(24, 1200, 1100, 1300), p(36, 980, 850, 1100), p(60, 820, 600, 1000)]).tone).toBe("warning")
    })

    it("already below 1000 at 12 months", () => {
        expect(trajectorySummary(950, [p(24, 800, 700, 900), p(36, 700, 600, 800), p(60, 600, 520, 700)]).text)
            .toBe("Already below 1000 cells/mm² at 12 months (950) and predicted to fall to 600 by month 60 (5 years).")
    })

    it("predicted to reach the failure level (G0003, red case)", () => {
        expect(trajectorySummary(1000, [p(24, 512, 459, 606), p(36, 357, 280, 433), p(60, 337, 220, 446)])).toEqual({
            tone: "danger", text: "Predicted to reach the 500 cells/mm² failure level by month 36 (3 years): 357.",
        })
    })
})
