import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { getCaseRun, listModuleRuns, type ModuleRun } from "@/api/cases"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listModuleRuns: vi.fn(),
    getCaseRun: vi.fn(),
}))

function gradingRun(id: string, tissueId: string, grade: string, at: string): ModuleRun {
    return {
        run: { id, module: "grading", status: "completed", errorCode: null, imageId: "img", caseAnalysisId: null, createdAt: at, headline: { grade } },
        caseId: `case-${tissueId}`,
        tissueId,
    }
}

beforeEach(() => {
    vi.mocked(listModuleRuns).mockImplementation(async (_module, options = {}) => {
        if (options.tissueId === "12657L") return { items: [gradingRun("r2", "12657L", "B", "2026-10-19T10:00:00Z")], nextBefore: null }
        if (options.before) return { items: [gradingRun("r3", "12658R", "A+", "2026-10-18T10:00:00Z")], nextBefore: null }
        return { items: [gradingRun("r1", "12656R", "A", "2026-10-20T10:00:00Z")], nextBefore: "2026-10-20T10:00:00Z" }
    })
})

describe("Previous results on a module page", () => {
    it("lists earlier results, loads older ones and searches by tissue ID", async () => {
        const user = userEvent.setup()
        renderApp("/grading", makeAuth({ user: makeUser("NURSE") }))

        const card = (await screen.findByRole("heading", { name: "Previous results" })).closest("section")!
        expect(await within(card).findByText("12656R")).toBeInTheDocument()
        expect(within(card).getByText("Grade A")).toBeInTheDocument()
        expect(vi.mocked(listModuleRuns).mock.calls[0][0]).toBe("grading")

        await user.click(within(card).getByRole("button", { name: "Load older results" }))
        expect(await within(card).findByText("12658R")).toBeInTheDocument()
        expect(within(card).queryByRole("button", { name: "Load older results" })).not.toBeInTheDocument()

        await user.type(within(card).getByLabelText("Search by tissue ID"), " 12657l ")
        await user.click(within(card).getByRole("button", { name: "Search" }))
        expect(await within(card).findByText("12657L")).toBeInTheDocument()
        expect(within(card).queryByText("12656R")).not.toBeInTheDocument()
        expect(vi.mocked(listModuleRuns).mock.calls.at(-1)?.[1]).toMatchObject({ tissueId: "12657L" })
    })

    it("checks the tissue ID before searching", async () => {
        const user = userEvent.setup()
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))

        const card = (await screen.findByRole("heading", { name: "Previous results" })).closest("section")!
        await within(card).findByText("12656R")
        const calls = vi.mocked(listModuleRuns).mock.calls.length
        await user.type(within(card).getByLabelText("Search by tissue ID"), "CASE-1")
        await user.click(within(card).getByRole("button", { name: "Search" }))

        expect(await within(card).findByRole("alert")).toHaveTextContent("five digits followed by R or L")
        expect(vi.mocked(listModuleRuns).mock.calls.length).toBe(calls)
    })

    it("opens an earlier result as its report", async () => {
        vi.mocked(getCaseRun).mockResolvedValue({
            summary: gradingRun("r1", "12656R", "A", "2026-10-20T10:00:00Z").run,
            inputs: { ECD_CD_cells_per_mm2: 2400 },
            result: {
                analysisId: "r1", caseId: "12656R", status: "completed", imageValidation: null, grade: "A",
                method: "hybrid_random_forest_24_resnet50", modelProbabilities: { A: 0.7, B: 0.3 },
                featuresUsed: {}, featuresNotRecorded: [], warnings: [],
                ecdReference: {
                    status: "completed", grade: "A", method: "ecd_threshold_tree", ecdUsed: 2400,
                    ecdBand: { lowerExclusive: 2232, upperInclusive: 2497 }, bandDistribution: { A: 1 },
                    bandTrainingTissues: 94, reviewRequired: false, message: "ECD only.",
                },
                reviewRequired: false, message: "Specialist confirmation required.", explanation: null,
            },
        })
        const user = userEvent.setup()
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))

        const card = (await screen.findByRole("heading", { name: "Previous results" })).closest("section")!
        await user.click(await within(card).findByRole("button", { name: "View report" }))

        expect(vi.mocked(getCaseRun).mock.calls[0]).toEqual(["case-12656R", "grading", "r1"])
        expect(await screen.findByRole("region", { name: "Inputs for this run" })).toBeInTheDocument()
        expect(await within(card).findByText(/Results for case/)).toHaveTextContent("12656R")
    })
})
