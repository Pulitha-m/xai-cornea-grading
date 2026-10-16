import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { analyzeCornea, type AnalyzeResponse } from "@/api/analysis"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

// Keep the real ECD range constants (used by the form validation); mock only the network call.
vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeCornea: vi.fn(),
}))

const GRADING_MESSAGE =
    "Grade based on ECD only (cut points 2232, 2497 cells/mm²). Slit-lamp findings and other morphology are not considered and may justify a lower grade. Specialist confirmation required."

const RESPONSE: AnalyzeResponse = {
    caseId: "CASE-042",
    status: "completed",
    cellular: { status: "completed", error: null, cellCount: 312, ecd: 2487.6, coefficientOfVariation: 0.3, hexagonality: 0.7 },
    grading: {
        status: "completed",
        error: null,
        grade: "A",
        method: "ecd_threshold_tree",
        ecdUsed: 2400,
        ecdBand: { lowerExclusive: 2232, upperInclusive: 2497 },
        bandDistribution: { "A+": 0.021, A: 0.894, B: 0.085 },
        bandTrainingTissues: 94,
        reviewRequired: false,
        message: GRADING_MESSAGE,
    },
    disease: { status: "failed", error: "Traceback: model weights missing", disease: null, severity: null, confidence: null },
    recommendation: { status: "completed", error: null, recommendation: "Suitable for further evaluation", confidence: 0.88 },
}

const REVIEW_REQUIRED: AnalyzeResponse = {
    ...RESPONSE,
    cellular: { status: "not_implemented", error: "Cellular analysis is not implemented yet.", cellCount: null, ecd: null, coefficientOfVariation: null, hexagonality: null },
    grading: {
        status: "review_required",
        error: null,
        grade: null,
        method: "ecd_threshold_tree",
        ecdUsed: null,
        ecdBand: null,
        bandDistribution: null,
        bandTrainingTissues: null,
        reviewRequired: true,
        message: "ECD is required for automated grading. Grade this tissue manually.",
    },
}

async function runAnalysis(ecd = "2400") {
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText("Image URL"), "https://images.test/cornea.png")
    await user.type(screen.getByLabelText("Case ID"), "CASE-042")
    if (ecd) {
        await user.type(screen.getByLabelText("ECD (cells/mm²)"), ecd)
    }
    await user.click(screen.getByRole("button", { name: "Analyse" }))
}

function moduleCard(title: string) {
    return screen.getByRole("region", { name: title })
}

describe("AnalysisPage", () => {
    it("shows each module's results in structured panels", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis()

        expect(await screen.findByRole("heading", { name: /Results for case CASE-042/ })).toBeInTheDocument()
        expect(analyzeCornea).toHaveBeenCalledWith({ imageUrl: "https://images.test/cornea.png", caseId: "CASE-042", ecd: 2400 })

        const cellular = within(moduleCard("Cellular analysis"))
        expect(cellular.getByText("2,488", { exact: false })).toHaveTextContent("2,488cells/mm²")
        expect(cellular.getByText("312")).toBeInTheDocument()
        expect(cellular.getByText("30%")).toBeInTheDocument()
        expect(cellular.getByText("70%")).toBeInTheDocument()

        expect(within(moduleCard("Recommendation")).getByText("Suitable for further evaluation")).toBeInTheDocument()
    })

    it("shows the ECD-based grade with its band and training distribution instead of a confidence", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis()

        const grade = within(await screen.findByRole("region", { name: "Cornea grade" }))
        expect(grade.getByText("Predicted grade").parentElement).toHaveTextContent(/^Predicted gradeA$/)
        expect(grade.getByText("2,232 < ECD ≤ 2,497")).toBeInTheDocument()
        expect(grade.getByText("89%")).toBeInTheDocument()
        expect(grade.getByText(/94 training tissues — not model confidence/)).toBeInTheDocument()
        expect(grade.getByText(/Specialist confirmation required/)).toBeInTheDocument()
        expect(grade.queryByRole("meter")).not.toBeInTheDocument()
    })

    it("sends no ECD when the field is blank and shows that manual grading is required", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(REVIEW_REQUIRED)
        renderApp("/analysis", makeAuth({ user: makeUser("NURSE") }))

        await runAnalysis("")

        const grade = within(await screen.findByRole("region", { name: "Cornea grade" }))
        expect(analyzeCornea).toHaveBeenLastCalledWith({ imageUrl: "https://images.test/cornea.png", caseId: "CASE-042", ecd: null })
        expect(grade.getByText("Manual grading required")).toBeInTheDocument()
        expect(grade.getByText(/Grade this tissue manually/)).toBeInTheDocument()
        expect(within(moduleCard("Cellular analysis")).getByText("This module is not available yet.")).toBeInTheDocument()
    })

    it("rejects an out-of-range ECD without running the analysis", async () => {
        vi.mocked(analyzeCornea).mockClear()
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis("7000")

        expect(await screen.findByRole("alert")).toHaveTextContent(/at most 6000/)
        expect(analyzeCornea).not.toHaveBeenCalled()
    })

    it("reports a failed module without exposing its internal error", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("NURSE") }))

        await runAnalysis()

        const disease = within(await screen.findByRole("region", { name: "Disease screening" }))
        expect(disease.getByText("Failed")).toBeInTheDocument()
        expect(disease.getByText(/could not complete the analysis/)).toBeInTheDocument()
        expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    })

    it("is not available to roles without the analysis permission", async () => {
        renderApp("/analysis", makeAuth({ user: makeUser("SUPPORT_STAFF") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
        expect(screen.queryByLabelText("Image URL")).not.toBeInTheDocument()
    })

    it("is linked from the clinical dashboard and navigation", async () => {
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("DOCTOR") }))

        expect(await screen.findByRole("link", { name: /Open workspace/ })).toHaveAttribute("href", "/analysis")
        expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("AI analysis")
    })
})
