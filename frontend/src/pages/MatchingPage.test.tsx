import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { getRecommendationRun, listRecommendationRuns, recommendMatch, type MatchResponse } from "@/api/recommendation"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listCandidates: vi.fn().mockResolvedValue([]),
}))
vi.mock(import("@/api/recommendation"), async (importOriginal) => ({
    ...(await importOriginal()),
    recommendMatch: vi.fn(),
    listRecommendationRuns: vi.fn(),
    getRecommendationRun: vi.fn(),
}))

const RANKED: MatchResponse = {
    analysisId: "run-2",
    requestId: "Q0001",
    ranked: [
        { rank: 1, recordId: "R0001", grade: "A", mlScore: 1.09, matchScore: 0.86, mcdaRank: 1, gradeGap: 0,
            criterionScores: { grade_fit: 1 }, reasons: ["grade fit 1.00"], why: [{ reason: "grade match", effect: 0.4 }],
            whyText: "grade match (+0.40)", counterfactual: null, flags: [] },
        { rank: 2, recordId: "R0002", grade: "A", mlScore: 0.03, matchScore: 0.8, mcdaRank: 2, gradeGap: 0,
            criterionScores: { grade_fit: 1 }, reasons: ["grade fit 1.00"], why: [{ reason: "freshness", effect: -0.2 }],
            whyText: "freshness (-0.20)", counterfactual: "would be #1 if: stored 2 fewer days",
            flags: ["serology not confirmed"] },
    ],
    excluded: [{ recordId: "R0003", reason: "positive serology" }],
    weightsUsed: { grade_fit: 0.35 },
    endotheliumConsidered: true,
    methodUsed: "ml",
    model: "matching-ranker-logistic",
    modelSummary: null,
    disclaimer: "Decision support only. The final allocation decision rests with the clinician.",
}

async function fillRow(user: ReturnType<typeof userEvent.setup>, row: number, id: string, serology?: string) {
    await user.type(screen.getByLabelText(`Tissue ID, row ${row}`), id)
    await user.selectOptions(screen.getByLabelText(`Grade, row ${row}`), "A")
    await user.type(screen.getByLabelText(`ECD, row ${row}`), "2800")
    if (serology) await user.selectOptions(screen.getByLabelText(`Serology clear, row ${row}`), serology)
}

beforeEach(() => {
    vi.mocked(recommendMatch).mockReset()
    vi.mocked(listRecommendationRuns).mockResolvedValue({ items: [], nextBefore: null })
})

describe("MatchingPage", () => {
    it("is in the navigation for clinical roles and is no longer 'coming soon'", async () => {
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        expect(await screen.findByRole("link", { name: /Recipients & matching/ })).toHaveAttribute("href", "/recipients")
        expect(screen.getByRole("heading", { name: "Recipients & matching", level: 1 })).toBeInTheDocument()
    })

    it("is not offered to support staff", async () => {
        renderApp("/support/dashboard", makeAuth({ user: makeUser("SUPPORT_STAFF") }))
        await screen.findByRole("navigation")
        expect(screen.queryByRole("link", { name: /Recipients & matching/ })).not.toBeInTheDocument()
    })

    it("sends the request and corneas and shows the ranking, reasons and exclusions", async () => {
        vi.mocked(recommendMatch).mockResolvedValue(RANKED)
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()

        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "+ Add cornea" }))
        await fillRow(user, 3, "R0003", "No")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const ranking = within(await screen.findByRole("region", { name: "Ranking for Q0001" }))
        expect(ranking.getByText("#1")).toBeInTheDocument()
        expect(ranking.getByText("R0001")).toBeInTheDocument()
        expect(ranking.getByText("serology not confirmed")).toBeInTheDocument()
        expect(ranking.getByText("Best option")).toBeInTheDocument()
        expect(ranking.getByText("Best option for this request, ahead of #2.")).toBeInTheDocument()
        const standsOut = within(ranking.getByRole("list", { name: "Stands out for" }))
        expect(standsOut.getAllByRole("listitem").map((li) => li.textContent))
            .toEqual(["closer to the requested grade", "fresher (fewer days in storage)"])
        expect(ranking.getByText("Ranked below #1.")).toBeInTheDocument()
        expect(within(ranking.getByRole("list", { name: "Held back by" })).getByText("further from the requested grade"))
            .toBeInTheDocument()
        // Changes to the tissue itself are not actionable, so they are not offered as a reason.
        expect(ranking.queryByText(/stored 2 fewer days/)).not.toBeInTheDocument()
        const excluded = within(screen.getByRole("region", { name: "Excluded: not eligible for transplant (1)" }))
        expect(excluded.getByText("R0003")).toBeInTheDocument()
        expect(excluded.getByText("Positive serology")).toBeInTheDocument()
        expect(screen.queryByText(/not ranked/i)).not.toBeInTheDocument()

        const sent = vi.mocked(recommendMatch).mock.calls[0][0]
        expect(sent.request).toEqual({ requestId: null, requestedGrade: "A", surgeryType: "PK", urgency: "Routine" })
        expect(screen.getByLabelText("Request ID")).toHaveValue("Q0001")
        expect(sent.method).toBe("ml")
        expect(sent.candidates.map((c) => [c.recordId, c.serologyClear, c.ecd, c.cv]))
            .toEqual([["R0001", "Yes", 2800, null], ["R0002", "Unknown", 2800, null], ["R0003", "No", 2800, null]])
    })

    it("shows the reasons, criterion scores and model notes for a cornea", async () => {
        vi.mocked(recommendMatch).mockResolvedValue({
            ...RANKED, endotheliumConsidered: false,
            modelSummary: { evaluation: "10x 5-fold grouped CV over 186 requests", ml_top3: 0.43, mcda_top3: 0.387 },
        })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        expect(await screen.findByText(/does not transplant the endothelium, so the clinician-priority cross-check does not score it/)).toBeInTheDocument()
        await user.click(screen.getByRole("button", { name: "Details for R0002" }))
        const details = within(screen.getByRole("region", { name: "Details for R0002" }))
        expect(details.getByText("freshness")).toBeInTheDocument()
        expect(details.getByText("-0.20")).toBeInTheDocument()
        expect(details.getByText("Cross-check against clinician priorities:").parentElement).toHaveTextContent("#2")
        expect(details.getByText("grade fit")).toBeInTheDocument()
        expect(screen.getByText(/Validated by cross-validation against historical NEBSL allocations/)).toHaveTextContent("top 3 for 43% of requests")
        expect(screen.getByText(/Cross-checked against clinician priorities: grade fit 35%/)).toBeInTheDocument()
        // Wording rule: the output is never presented as validated or reviewed by clinicians.
        expect(screen.queryByText(/validated with clinician|reviewed by clinician|MCDA/i)).not.toBeInTheDocument()
    })

    it("shows one ranked list and says where the recommended cornea stands by clinician priorities", async () => {
        vi.mocked(recommendMatch).mockResolvedValue({
            ...RANKED,
            ranked: [{ ...RANKED.ranked[0], mcdaRank: 2 }, { ...RANKED.ranked[1], mcdaRank: 1 }],
        })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const ranking = within(await screen.findByRole("region", { name: "Ranking for Q0001" }))
        expect(ranking.queryByRole("columnheader", { name: /MCDA rank/i })).not.toBeInTheDocument()
        expect(ranking.queryByText("Methods differ")).not.toBeInTheDocument()
        expect(ranking.getByText(/ranks #2\. Review its reasons below before deciding\./)).toBeInTheDocument()
        expect(screen.queryByLabelText("Ranking method")).not.toBeInTheDocument()

        await user.click(ranking.getByRole("button", { name: "Details for R0001" }))
        const details = within(screen.getByRole("region", { name: "Details for R0001" }))
        expect(details.getByText("Cross-check against clinician priorities:").parentElement).toHaveTextContent("#2")
    })

    it("says when the recommended cornea is also first by clinician priorities", async () => {
        vi.mocked(recommendMatch).mockResolvedValue(RANKED)
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const ranking = within(await screen.findByRole("region", { name: "Ranking for Q0001" }))
        expect(ranking.getByText(/is also first\./)).toBeInTheDocument()
        expect(vi.mocked(recommendMatch).mock.calls[0][0].method).toBe("ml")
    })

    it("rejects impossible values and a tissue ID used twice instead of calling the server", async () => {
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001")
        await user.type(screen.getByLabelText("Days in storage, row 1"), "400")
        await fillRow(user, 2, "r0001")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        expect(await screen.findByText(
            "Not possible: R0001: days in storage must be between 0 and 60; tissue ID R0001 is used twice.",
        )).toBeInTheDocument()
        expect(recommendMatch).not.toHaveBeenCalled()
    })

    it("shows the values to check above the ranking", async () => {
        vi.mocked(recommendMatch).mockResolvedValue({ ...RANKED, warnings: ["R0002: stored 20 days, longer than the usual 14-day limit."] })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const check = within(await screen.findByRole("region", { name: "Check these values" }))
        expect(check.getByText("R0002: stored 20 days, longer than the usual 14-day limit.")).toBeInTheDocument()
    })

    it("accepts only study codes, never a real NEBSL tissue ID", async () => {
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "12656R")
        await fillRow(user, 2, "T2")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const alert = await screen.findByText(/^Not possible:/)
        expect(alert).toHaveTextContent("12656R looks like a real NEBSL tissue ID; enter the study code instead (R + 4 digits, e.g. R0012)")
        expect(alert).toHaveTextContent("Tissue ID T2 must be R followed by 4 digits, e.g. R0012")
        expect(recommendMatch).not.toHaveBeenCalled()
    })

    it("sends tissue IDs trimmed and upper-cased", async () => {
        vi.mocked(recommendMatch).mockResolvedValue(RANKED)
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "r0001")
        await fillRow(user, 2, "R0002")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        await screen.findByRole("region", { name: "Ranking for Q0001" })
        const sent = vi.mocked(recommendMatch).mock.calls[0][0]
        expect(sent.candidates.map((c) => c.recordId)).toEqual(["R0001", "R0002"])
    })

    it("assigns the request ID on the first ranking, keeps it on re-ranking, and clears it for a new request", async () => {
        vi.mocked(recommendMatch).mockResolvedValue({ ...RANKED, requestId: "Q0007" })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        const field = await screen.findByLabelText("Request ID")
        expect(field).toHaveAttribute("readonly")
        expect(screen.getByText("Assigned automatically when you rank.")).toBeInTheDocument()
        await fillRow(user, 1, "R0001", "Yes")
        await fillRow(user, 2, "R0002")

        await user.click(screen.getByRole("button", { name: "Rank corneas" }))
        await screen.findByRole("region", { name: "Ranking for Q0007" })
        expect(field).toHaveValue("Q0007")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))
        await screen.findByRole("region", { name: "Ranking for Q0007" })
        const calls = vi.mocked(recommendMatch).mock.calls.map((c) => c[0].request.requestId)
        expect(calls).toEqual([null, "Q0007"])

        await user.click(screen.getByRole("button", { name: "New request" }))
        expect(screen.getByLabelText("Request ID")).toHaveValue("")
        expect(screen.getByLabelText("Tissue ID, row 1")).toHaveValue("")
        expect(screen.queryByRole("region", { name: "Ranking for Q0007" })).not.toBeInTheDocument()
    })

    it("says when no cornea is eligible instead of showing an empty ranking", async () => {
        vi.mocked(recommendMatch).mockResolvedValue({
            ...RANKED, ranked: [],
            excluded: [{ recordId: "R0001", reason: "positive serology" }, { recordId: "R0002", reason: "positive serology" }],
        })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await screen.findByLabelText("Request ID")
        await fillRow(user, 1, "R0001", "No")
        await fillRow(user, 2, "R0002", "No")
        await user.click(screen.getByRole("button", { name: "Rank corneas" }))

        const ranking = within(await screen.findByRole("region", { name: "Ranking for Q0001" }))
        expect(ranking.getByText("No eligible cornea for this request")).toBeInTheDocument()
        expect(ranking.getByText(/All 2 corneas were excluded by the safety rule/)).toBeInTheDocument()
        expect(ranking.queryByRole("table")).not.toBeInTheDocument()
    })

    it("lists previous rankings and reopens one in full", async () => {
        vi.mocked(listRecommendationRuns).mockResolvedValue({
            items: [
                { id: "run-2", kind: "match", subjectId: "Q0001", status: "completed", errorCode: null, methodUsed: "ml",
                    topRecordId: "R0001", alert: null, nextVisitMonths: null, requestedBy: "Dr Silva", createdAt: "2026-10-20T09:00:00Z" },
                { id: "run-1", kind: "match", subjectId: "Q0000", status: "rejected", errorCode: "DUPLICATE_TISSUE_ID", methodUsed: null,
                    topRecordId: null, alert: null, nextVisitMonths: null, requestedBy: "Dr Silva", createdAt: "2026-10-19T09:00:00Z" },
            ],
            nextBefore: null,
        })
        vi.mocked(getRecommendationRun).mockResolvedValue({ summary: { id: "run-2", kind: "match" } as never, inputs: {}, result: RANKED })
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()

        const previous = within(await screen.findByRole("region", { name: "Previous runs" }))
        expect(await previous.findByText("Q0001")).toBeInTheDocument()
        expect(previous.getByText("R0001")).toBeInTheDocument()
        expect(previous.getByText("duplicate tissue id")).toBeInTheDocument()
        expect(previous.queryByRole("button", { name: "Open run Q0000" })).not.toBeInTheDocument()

        await user.click(previous.getByRole("button", { name: "Open run Q0001" }))
        expect(await previous.findByRole("region", { name: "Ranking for Q0001" })).toBeInTheDocument()
        expect(getRecommendationRun).toHaveBeenCalledWith("run-2")

        await user.type(previous.getByLabelText("Search by request id"), "Q0001")
        await user.click(previous.getByRole("button", { name: "Search" }))
        expect(vi.mocked(listRecommendationRuns)).toHaveBeenLastCalledWith("match", expect.objectContaining({ subject: "Q0001" }))
    })

    it("requires a tissue ID on every row", async () => {
        renderApp("/recipients", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()
        await user.click(await screen.findByRole("button", { name: "Rank corneas" }))

        expect(await screen.findByText(/Missing or not a number: row 1: tissue ID, row 2: tissue ID/)).toBeInTheDocument()
        expect(recommendMatch).not.toHaveBeenCalled()
    })
})
