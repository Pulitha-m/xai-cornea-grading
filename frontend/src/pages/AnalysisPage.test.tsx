import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { analyzeCornea, type AnalyzeResponse } from "@/api/analysis"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock("@/api/analysis", () => ({ analyzeCornea: vi.fn() }))

const RESPONSE: AnalyzeResponse = {
    caseId: "CASE-042",
    status: "completed",
    cellular: { status: "completed", error: null, cellCount: 312, ecd: 2487.6, coefficientOfVariation: 0.3, hexagonality: 0.7 },
    grading: { status: "completed", error: null, grade: "A", confidence: 0.92 },
    disease: { status: "failed", error: "Traceback: model weights missing", disease: null, severity: null, confidence: null },
    recommendation: { status: "completed", error: null, recommendation: "Suitable for further evaluation", confidence: 0.88 },
}

async function runAnalysis() {
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText("Image URL"), "https://images.test/cornea.png")
    await user.type(screen.getByLabelText("Case ID"), "CASE-042")
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
        expect(analyzeCornea).toHaveBeenCalledWith({ imageUrl: "https://images.test/cornea.png", caseId: "CASE-042" })

        const cellular = within(moduleCard("Cellular analysis"))
        expect(cellular.getByText("2,488", { exact: false })).toHaveTextContent("2,488cells/mm²")
        expect(cellular.getByText("312")).toBeInTheDocument()
        expect(cellular.getByText("30%")).toBeInTheDocument()
        expect(cellular.getByText("70%")).toBeInTheDocument()

        const grade = within(moduleCard("Cornea grade"))
        expect(grade.getByText("A")).toBeInTheDocument()
        expect(grade.getByRole("meter", { name: "Model confidence" })).toHaveAttribute("aria-valuenow", "92")

        expect(within(moduleCard("Recommendation")).getByText("Suitable for further evaluation")).toBeInTheDocument()
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
