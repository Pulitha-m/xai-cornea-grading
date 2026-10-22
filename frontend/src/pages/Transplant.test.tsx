import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { getCase, listCandidates, listCaseImages, type DonorCase } from "@/api/cases"
import type { FollowupResponse } from "@/api/recommendation"
import {
    allocateGraft,
    listGraftFollowups,
    listGrafts,
    matchFromCases,
    recordGraftVisit,
    runGraftFollowup,
    type Graft,
} from "@/api/transplants"
import { SHOW_GRAFTS_ON_FOLLOWUP, SHOW_STOCK_ON_MATCHING } from "@/lib/feature-flags"
import { FEATURES } from "@/lib/grading-features"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listCandidates: vi.fn(),
    getCase: vi.fn(),
    listCaseImages: vi.fn(),
}))
vi.mock(import("@/api/transplants"), async (importOriginal) => ({
    ...(await importOriginal()),
    matchFromCases: vi.fn(),
    allocateGraft: vi.fn(),
    listGrafts: vi.fn(),
    recordGraftVisit: vi.fn(),
    runGraftFollowup: vi.fn(),
    listGraftFollowups: vi.fn(),
}))

const CASE_ID = "11111111-1111-1111-1111-111111111111"

const GRAFT: Graft = {
    id: "graft-1", caseId: CASE_ID, tissueId: "12656R", requestId: "Q0001", procedure: "PK",
    indication: "Fuchs/Endothelial", surgeryDate: "2026-10-01", rejectionBy12m: null,
    donorAge: 54, baselineEcd: 2400, baselineCv: 30, baselineHex: 60,
    visits: [{ month: 6, ecd: 1700, cv: 42, hex: 50, visitDate: null }],
    missing: ["12-month visit"], latestFollowup: null, createdAt: "2026-10-20T08:00:00Z",
}

const RED: FollowupResponse = {
    analysisId: "run-1", graftId: "graft-1", alert: "red", nextVisitMonths: 3,
    rulesFired: ["12-month ECD < 750"], actions: ["Repeat specular microscopy at the next visit"],
    predictedEcd: [{ months: 24, ecd: 542, low: 485, high: 641 }], bandLevel: "10-90%",
    risk: [{ outcome: "graft_failure", withinMonths: 12, probability: 0.41 }],
    reasons: { trajectory: [], graftFailure: [], lowEcd: [] }, counterfactuals: [],
    alertThresholds: { red_failure_risk_12m: 0.2, amber_failure_risk_24m: 0.05, amber_low_ecd_risk_24m: 0.3 },
    modelSummary: {}, model: "followup-12m-visit", modelVersion: "2026-10-20", rulesVersion: "x", dataSource: "simulated",
    disclaimer: "Decision support only.",
}

beforeEach(() => {
    vi.mocked(listCandidates).mockResolvedValue([{
        recordId: CASE_ID, tissueId: "12656R", grade: "A", ecd: 2400, cv: 30, hex: 60, donorAge: 54,
        deathToPreservationH: 6, daysInStorage: 2, serologyClear: "Yes", diseaseFinding: "Normal",
    }])
    vi.mocked(listGraftFollowups).mockResolvedValue([])
})

describe("Matching from donor cases", () => {
    // The stock tab is hidden on the matching page for now; this runs again when the flag is turned back on.
    it.skipIf(!SHOW_STOCK_ON_MATCHING)("ranks the signed-off corneas by tissue ID and lets a doctor allocate one", async () => {
        vi.mocked(matchFromCases).mockResolvedValue({
            match: {
                analysisId: "match-1", requestId: "Q0001",
                ranked: [{
                    rank: 1, recordId: CASE_ID, grade: "A", mlScore: 0.9, matchScore: 0.8, mcdaRank: 1, gradeGap: 0,
                    criterionScores: {}, reasons: ["grade fits"], why: [], whyText: "Grade fits the request",
                    counterfactual: null, flags: [],
                }],
                excluded: [], weightsUsed: {}, endotheliumConsidered: true, methodUsed: "ml", model: "ranker",
                modelSummary: {}, disclaimer: "Decision support.",
            },
            tissueIds: { [CASE_ID]: "12656R" }, considered: 1, notInStock: 2,
        })
        vi.mocked(allocateGraft).mockResolvedValue({ ...GRAFT, visits: [], missing: ["6-month visit", "12-month visit"] })
        const user = userEvent.setup()
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))

        expect(await screen.findByText("1 signed-off cornea in stock.")).toBeInTheDocument()
        await user.type(screen.getByLabelText("Request ID"), "Q0001")
        await user.click(screen.getByRole("button", { name: "Rank corneas in stock" }))

        expect(vi.mocked(matchFromCases).mock.calls[0][0]).toMatchObject({ request: { requestId: "Q0001", requestedGrade: "A" }, method: "ml" })
        expect(await screen.findByRole("link", { name: "12656R" })).toHaveAttribute("href", `/cases/${CASE_ID}`)
        expect(screen.getByText(/2 other signed-off corneas are no longer in stock/)).toBeInTheDocument()

        const allocate = screen.getByRole("heading", { name: "Allocate a cornea" }).closest("section")!
        await user.selectOptions(within(allocate).getByLabelText("Indication"), "Failed/Re-graft")
        await user.click(within(allocate).getByRole("button", { name: "Allocate" }))

        expect(vi.mocked(allocateGraft).mock.calls[0][0]).toEqual({
            caseId: CASE_ID, requestId: "Q0001", procedure: "PK", indication: "Failed/Re-graft", surgeryDate: null, matchRunId: "match-1",
        })
        expect(await screen.findByText(/is allocated to request Q0001/)).toBeInTheDocument()
    })

    it("gives nurses the manual matching only", async () => {
        renderApp("/recipients", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByRole("button", { name: "Rank corneas" })).toBeInTheDocument()
        expect(screen.queryByRole("radio", { name: "Signed-off corneas in stock" })).not.toBeInTheDocument()
        expect(listCandidates).not.toHaveBeenCalled()
    })
})

describe("Follow-up of grafts", () => {
    // The graft list is hidden on the follow-up page for now; this runs again when the flag is turned back on.
    it.skipIf(!SHOW_GRAFTS_ON_FOLLOWUP)("records a visit and gets the recommendation for a graft", async () => {
        vi.mocked(listGrafts).mockResolvedValue([GRAFT])
        vi.mocked(recordGraftVisit).mockImplementation(async () => {
            const ready = { ...GRAFT, missing: [], visits: [...GRAFT.visits, { month: 12 as const, ecd: 1000, cv: 46, hex: 45, visitDate: null }] }
            vi.mocked(listGrafts).mockResolvedValue([ready])
            return ready
        })
        vi.mocked(runGraftFollowup).mockResolvedValue({
            summary: { runId: "run-1", status: "completed", errorCode: null, alert: "red", nextVisitMonths: 3, createdAt: "2026-10-20T09:00:00Z" },
            request: {
                graftId: "graft-1", procedure: "PK", indication: "Fuchs/Endothelial", donorAge: 54, baselineEcd: 2400,
                baselineCv: 30, baselineHex: 60, visit3m: null, visit6m: { ecd: 1700, cv: 42, hex: 50 },
                visit12m: { ecd: 1000, cv: 46, hex: 45 }, rejectionBy12m: false,
            },
            result: RED,
        })
        const user = userEvent.setup()
        renderApp("/post-transplant", makeAuth({ user: makeUser("NURSE") }))

        await user.click(await screen.findByRole("button", { name: "Follow up" }))
        expect(await screen.findByText("Still needed: 12-month visit.")).toBeInTheDocument()
        expect(screen.getByRole("button", { name: "Get follow-up recommendation" })).toBeDisabled()

        const visit12 = screen.getByRole("form", { name: "12-month visit" })
        await user.type(within(visit12).getByLabelText("ECD (cells/mm²)"), "1000")
        await user.type(within(visit12).getByLabelText("CV (%)"), "46")
        await user.type(within(visit12).getByLabelText("HEX (%)"), "45")
        await user.click(within(visit12).getByRole("button", { name: "Save" }))
        expect(vi.mocked(recordGraftVisit).mock.calls[0]).toEqual(["graft-1", 12, { ecd: 1000, cv: 46, hex: 45, visitDate: null }])

        const run = await screen.findByRole("button", { name: "Get follow-up recommendation" })
        await vi.waitFor(() => expect(run).toBeEnabled())
        await user.click(run)
        expect(await screen.findByText("Red alert")).toBeInTheDocument()
        expect(screen.getByText("Next visit in 3 months")).toBeInTheDocument()
    })
})

describe("Case Transplant tab", () => {
    const CASE: DonorCase = {
        id: CASE_ID, tissueId: "12656R",
        details: {
            donorAgeYears: 54, deathToPreservationHours: null, preservationDate: null, ecd: 2400, cv: null, hexPercent: null,
            sd: null, totalCellCount: null, totalAreaUm2: null,
            slitLamp: Object.fromEntries(FEATURES.filter((f) => f.group !== "konan").map((f) => [f.name, null])),
        },
        imageCount: 0, latestSignoff: { confirmedGrade: "A", diseaseFinding: "Normal", signedByName: "Dr", createdAt: "2026-10-20T08:00:00Z" },
        createdAt: "2026-10-20T08:00:00Z", updatedAt: "2026-10-20T08:00:00Z",
    }

    beforeEach(() => {
        vi.mocked(getCase).mockResolvedValue(CASE)
        vi.mocked(listCaseImages).mockResolvedValue([])
    })

    it("explains how to allocate a cornea that is not allocated yet", async () => {
        vi.mocked(listGrafts).mockResolvedValue([])
        const user = userEvent.setup()
        renderApp(`/cases/${CASE_ID}`, makeAuth({ user: makeUser("DOCTOR") }))

        await user.click(await screen.findByRole("tab", { name: "Transplant" }))
        expect(await screen.findByText("Not allocated")).toBeInTheDocument()
        expect(screen.getByRole("link", { name: "Go to Recipients & matching" })).toBeInTheDocument()
        expect(vi.mocked(listGrafts).mock.calls[0][0]).toBe(CASE_ID)
    })

    it("shows the graft of an allocated cornea", async () => {
        vi.mocked(listGrafts).mockResolvedValue([GRAFT])
        const user = userEvent.setup()
        renderApp(`/cases/${CASE_ID}`, makeAuth({ user: makeUser("NURSE") }))
        await user.click(await screen.findByRole("tab", { name: "Transplant" }))
        expect(await screen.findByRole("heading", { name: "Graft of tissue 12656R" })).toBeInTheDocument()
    })
})
