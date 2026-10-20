import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import {
    analyzeCase,
    getCase,
    listCaseImages,
    listCandidates,
    listCaseRuns,
    listSignoffs,
    openCase,
    recentCases,
    updateCaseDetails,
    type CaseAnalysisResponse,
    type DonorCase,
} from "@/api/cases"
import { FEATURES } from "@/lib/grading-features"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    openCase: vi.fn(),
    recentCases: vi.fn(),
    getCase: vi.fn(),
    updateCaseDetails: vi.fn(),
    listCaseImages: vi.fn(),
    fetchCaseImage: vi.fn(),
    analyzeCase: vi.fn(),
    listCaseRuns: vi.fn(),
    getCaseRun: vi.fn(),
    listSignoffs: vi.fn(),
    signOff: vi.fn(),
    getSerology: vi.fn(),
    updateSerology: vi.fn(),
    listCandidates: vi.fn(),
}))

const SLIT_LAMP = Object.fromEntries(FEATURES.filter((f) => f.group !== "konan").map((f) => [f.name, null]))

const CASE: DonorCase = {
    id: "case-1",
    tissueId: "12656R",
    details: {
        donorAgeYears: null, deathToPreservationHours: null, preservationDate: null,
        ecd: null, cv: null, hexPercent: null, sd: null, totalCellCount: null, totalAreaUm2: null,
        slitLamp: SLIT_LAMP,
    },
    imageCount: 1,
    latestSignoff: null,
    createdAt: "2026-10-20T08:00:00Z",
    updatedAt: "2026-10-20T08:00:00Z",
}

const IMAGE = { id: "img-1", contentType: "image/jpeg", sizeBytes: 1000, width: 1296, height: 972, uploadedBy: 1, uploadedAt: "2026-10-20T08:05:00Z" }

beforeEach(() => {
    vi.mocked(recentCases).mockResolvedValue([])
    vi.mocked(getCase).mockResolvedValue(CASE)
    vi.mocked(listCaseImages).mockResolvedValue([IMAGE])
    vi.mocked(listCaseRuns).mockResolvedValue([])
    vi.mocked(listSignoffs).mockResolvedValue([])
    vi.mocked(listCandidates).mockResolvedValue([])
})

describe("Donor cases", () => {
    it("checks the tissue ID format before opening a case", async () => {
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        await user.type(await screen.findByLabelText("Tissue ID"), "CASE-1")
        await user.click(screen.getByRole("button", { name: "Open case" }))

        expect(await screen.findByRole("alert")).toHaveTextContent("five digits followed by R or L")
        expect(openCase).not.toHaveBeenCalled()
    })

    it("opens the case for a normalised tissue ID and shows its workspace", async () => {
        vi.mocked(openCase).mockResolvedValue(CASE)
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("DOCTOR") }))

        await user.type(await screen.findByLabelText("Tissue ID"), " 12656r ")
        await user.click(screen.getByRole("button", { name: "Open case" }))

        expect(vi.mocked(openCase).mock.calls[0][0]).toBe("12656R")
        expect(await screen.findByRole("heading", { name: "Tissue 12656R" })).toBeInTheDocument()
    })

    it("is not available to non-clinical roles", async () => {
        renderApp("/cases", makeAuth({ user: makeUser("MANAGER") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
    })
})

describe("Case workspace", () => {
    it("saves the details once for every module", async () => {
        vi.mocked(updateCaseDetails).mockImplementation(async (_id, details) => ({ ...CASE, details }))
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("DOCTOR") }))

        await user.type(await screen.findByLabelText("Donor age (years)"), "54")
        await user.type(screen.getByLabelText("ECD (cells/mm²)"), "2400")
        await user.click(screen.getByRole("button", { name: "Save details" }))

        expect(await screen.findByText("Details saved.")).toBeInTheDocument()
        const [caseId, details] = vi.mocked(updateCaseDetails).mock.calls[0]
        expect(caseId).toBe("case-1")
        expect(details).toMatchObject({ donorAgeYears: 54, ecd: 2400, cv: null })
        expect(Object.keys(details.slitLamp)).toHaveLength(18)
    })

    it("runs the chosen modules and shows a failed module next to the others' results", async () => {
        vi.mocked(getCase).mockResolvedValue({ ...CASE, details: { ...CASE.details, ecd: 2400 } })
        const response: CaseAnalysisResponse = {
            id: "analysis-1",
            tissueId: "12656R",
            imageId: "img-1",
            modules: {
                grading: { status: "failed", errorCode: "INTERNAL_ERROR", message: "The grading analysis could not be completed. Try again later.", result: null },
                disease: { status: "rejected", errorCode: "CASE_DETAILS_MISSING", message: "Enter the Konan measurements.", result: null },
            },
            consistency: [{ code: "GRADE_DIFFERS_FROM_ECD_REFERENCE", message: "The model's grade (A) differs from the ECD reference grade (B)." }],
            createdAt: "2026-10-20T08:10:00Z",
        }
        vi.mocked(analyzeCase).mockResolvedValue(response)
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("NURSE") }))

        await user.click(await screen.findByRole("tab", { name: "Analyse" }))
        await user.click(await screen.findByLabelText("Cellular analysis"))
        await user.click(screen.getByRole("button", { name: "Run analysis" }))

        expect(vi.mocked(analyzeCase).mock.calls[0]).toEqual(["case-1", { imageId: "img-1", modules: ["grading", "disease"], forceDisease: false }])
        expect(await screen.findByText("For review: the modules disagree")).toBeInTheDocument()
        expect(screen.getByText(/differs from the ECD reference grade/)).toBeInTheDocument()
        const grading = screen.getByRole("heading", { name: "Cornea grading" }).closest("section")!
        expect(within(grading).getByText("Failed")).toBeInTheDocument()
        expect(screen.getByText("Enter the Konan measurements.")).toBeInTheDocument()
    })

    it("lists every saved run in the history", async () => {
        vi.mocked(listCaseRuns).mockResolvedValue([
            { id: "r1", module: "grading", status: "completed", errorCode: null, imageId: "img-1", caseAnalysisId: "a1", createdAt: "2026-10-20T08:10:00Z", headline: { grade: "A" } },
            { id: "r2", module: "disease", status: "failed", errorCode: "INTERNAL_ERROR", imageId: "img-1", caseAnalysisId: "a1", createdAt: "2026-10-20T08:09:00Z", headline: {} },
        ])
        const user = userEvent.setup()
        renderApp("/cases/case-1", makeAuth({ user: makeUser("DOCTOR") }))

        await user.click(await screen.findByRole("tab", { name: "History" }))

        expect(await screen.findByText("Grade A")).toBeInTheDocument()
        expect(screen.getByText("INTERNAL_ERROR")).toBeInTheDocument()
        expect(screen.getAllByText("Image 1")).toHaveLength(2)
    })
})
