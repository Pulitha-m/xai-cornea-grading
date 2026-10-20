import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import {
    getCase,
    getCaseRun,
    getSerology,
    listCandidates,
    listCaseImages,
    listCaseRuns,
    listSignoffs,
    recentCases,
    signOff,
    type DonorCase,
    type RunSummary,
} from "@/api/cases"
import { FEATURES } from "@/lib/grading-features"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    recentCases: vi.fn(),
    getCase: vi.fn(),
    listCaseImages: vi.fn(),
    fetchCaseImage: vi.fn(),
    listCaseRuns: vi.fn(),
    getCaseRun: vi.fn(),
    listSignoffs: vi.fn(),
    signOff: vi.fn(),
    getSerology: vi.fn(),
    updateSerology: vi.fn(),
    listCandidates: vi.fn(),
}))

const CASE: DonorCase = {
    id: "case-1",
    tissueId: "12656R",
    details: {
        donorAgeYears: null, deathToPreservationHours: null, preservationDate: null,
        ecd: 2400, cv: null, hexPercent: null, sd: null, totalCellCount: null, totalAreaUm2: null,
        slitLamp: Object.fromEntries(FEATURES.filter((f) => f.group !== "konan").map((f) => [f.name, null])),
    },
    imageCount: 1,
    latestSignoff: null,
    createdAt: "2026-10-20T08:00:00Z",
    updatedAt: "2026-10-20T08:00:00Z",
}

function run(module: RunSummary["module"], headline: Record<string, unknown>, id = `run-${module}`): RunSummary {
    return { id, module, status: "completed", errorCode: null, imageId: "img-1", caseAnalysisId: "a1", createdAt: "2026-10-20T08:10:00Z", headline }
}

beforeEach(() => {
    vi.mocked(recentCases).mockResolvedValue([])
    vi.mocked(getCase).mockResolvedValue(CASE)
    vi.mocked(listCaseImages).mockResolvedValue([
        { id: "img-1", contentType: "image/jpeg", sizeBytes: 1000, width: 1296, height: 972, uploadedBy: 1, uploadedAt: "2026-10-20T08:05:00Z" },
    ])
    vi.mocked(listCaseRuns).mockResolvedValue([])
    vi.mocked(listSignoffs).mockResolvedValue([])
    vi.mocked(listCandidates).mockResolvedValue([])
})

describe("Saved results", () => {
    it("shows a saved run as its report with labelled inputs, not raw JSON", async () => {
        vi.mocked(listCaseRuns).mockResolvedValue([run("grading", { grade: "B" })])
        vi.mocked(getCaseRun).mockResolvedValue({
            summary: run("grading", { grade: "B" }),
            inputs: { ECD_CD_cells_per_mm2: 2400, Stroma_Has_Scar: 1, CV: null },
            result: {
                analysisId: "run-grading", caseId: "12656R", status: "completed", imageValidation: null, grade: "B",
                method: "hybrid_random_forest_24_resnet50", modelProbabilities: { "A+": 0.05, A: 0.32, B: 0.63 },
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
        renderApp("/cases/case-1", makeAuth({ user: makeUser("NURSE") }))

        await user.click(await screen.findByRole("tab", { name: "History" }))
        await user.click(await screen.findByRole("button", { name: "Details" }))

        const inputs = await screen.findByRole("region", { name: "Inputs for this run" })
        expect(within(inputs).getByText("ECD")).toBeInTheDocument()
        expect(within(inputs).getByText("2,400 cells/mm²")).toBeInTheDocument()
        expect(within(inputs).getByText("Yes")).toBeInTheDocument()
        expect(within(inputs).getByText("Not recorded")).toBeInTheDocument()
        expect(await screen.findByText(/Results for case/)).toHaveTextContent("12656R")
        expect(screen.queryByText(/"grade"/)).not.toBeInTheDocument()
    })
})

describe("Sign-off", () => {
    it("lets a doctor sign off, pre-filled from the latest analysis", async () => {
        vi.mocked(listCaseRuns).mockResolvedValue([
            run("grading", { grade: "A" }),
            run("disease", { normal: false, detected: ["Guttata"] }),
        ])
        vi.mocked(signOff).mockResolvedValue({
            id: "s1", confirmedGrade: "A", diseaseFinding: "Guttata", ecd: 2400, cv: null, hexPercent: null, notes: null,
            signedBy: 1, signedByName: "Test DOCTOR", caseAnalysisId: "a1", createdAt: "2026-10-20T09:00:00Z",
        })
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("DOCTOR") }))

        await user.click(await screen.findByRole("tab", { name: "Sign-off" }))
        expect(await screen.findByLabelText("Confirmed grade")).toHaveValue("A")
        expect(screen.getByLabelText("Disease finding")).toHaveValue("Guttata")
        expect(screen.getByLabelText("ECD (cells/mm²)")).toHaveValue("2400")
        await user.click(screen.getByRole("button", { name: "Sign off" }))

        expect(await screen.findByText("Signed off.")).toBeInTheDocument()
        expect(vi.mocked(signOff).mock.calls[0]).toEqual(["case-1", {
            confirmedGrade: "A", diseaseFinding: "Guttata", ecd: 2400, cv: null, hexPercent: null, notes: null, caseAnalysisId: "a1",
        }])
    })

    it("shows nurses the sign-offs but neither the form nor serology", async () => {
        vi.mocked(listSignoffs).mockResolvedValue([{
            id: "s1", confirmedGrade: "B", diseaseFinding: "Normal", ecd: 2300, cv: 30, hexPercent: 60, notes: "Checked twice",
            signedBy: 2, signedByName: "Dr Silva", caseAnalysisId: null, createdAt: "2026-10-20T09:00:00Z",
        }])
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByLabelText("Donor age (years)")).toBeInTheDocument()
        expect(screen.queryByRole("button", { name: "Show serology" })).not.toBeInTheDocument()
        await user.click(screen.getByRole("tab", { name: "Sign-off" }))
        expect(await screen.findByText("Grade B · Normal")).toBeInTheDocument()
        expect(screen.getByText("Checked twice")).toBeInTheDocument()
        expect(screen.queryByRole("button", { name: "Sign off" })).not.toBeInTheDocument()
    })
})

describe("Serology and candidates", () => {
    it("fetches serology only when a doctor asks for it", async () => {
        vi.mocked(getSerology).mockResolvedValue({ hiv: "Negative", hbv: "Positive", hcv: null, syphilis: null, serologyClear: false })
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("DOCTOR") }))

        await user.click(await screen.findByRole("button", { name: "Show serology" }))
        expect(getSerology).toHaveBeenCalledTimes(1)
        expect(await screen.findByText("Positive result")).toBeInTheDocument()
        expect(screen.getByLabelText("Hepatitis B (HBsAg)")).toHaveValue("Positive")
    })

    it("lists signed-off corneas for doctors on the cases page", async () => {
        vi.mocked(listCandidates).mockResolvedValue([{
            recordId: "case-1", tissueId: "12656R", grade: "A", ecd: 2400, cv: 30, hex: 60, donorAge: 54,
            deathToPreservationH: 6, daysInStorage: 3, serologyClear: "Yes", diseaseFinding: "Normal",
        }])
        renderApp("/cases", makeAuth({ user: makeUser("DOCTOR") }))

        const card = (await screen.findByRole("heading", { name: "Signed-off corneas" })).closest("section")!
        expect(await within(card).findByText("12656R")).toBeInTheDocument()
        expect(within(card).getByText("Clear")).toBeInTheDocument()
    })

    it("does not list candidates for nurses", async () => {
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByRole("heading", { name: "Open a case" })).toBeInTheDocument()
        expect(screen.queryByRole("heading", { name: "Signed-off corneas" })).not.toBeInTheDocument()
        expect(listCandidates).not.toHaveBeenCalled()
    })
})
