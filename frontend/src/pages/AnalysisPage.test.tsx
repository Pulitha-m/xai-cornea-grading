import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { analyzeCornea, uploadImage, type AnalyzeResponse } from "@/api/analysis"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

// Keep the real constants (used by validation); mock only the network calls.
vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeCornea: vi.fn(),
    uploadImage: vi.fn(),
}))

const GRADING_MESSAGE =
    "Grade based on ECD only (cut points 2232, 2497 cells/mm²). Slit-lamp findings and other morphology are not considered and may justify a lower grade. Specialist confirmation required."

const RESPONSE: AnalyzeResponse = {
    analysisId: "run-1",
    caseId: "CASE-042",
    status: "partial",
    imageValidation: { domainStatus: "VALID_CORNEAL_IMAGE", qualityAssessed: false, width: 1296, height: 972, format: "JPEG" },
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

const JPEG_BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])

function jpeg(name = "endothelium.jpg") {
    return new File([JPEG_BYTES], name, { type: "image/jpeg" })
}

async function runAnalysis({ ecd = "2400", file = jpeg() }: { ecd?: string; file?: File } = {}) {
    const user = userEvent.setup()
    await user.upload(await screen.findByLabelText("Specular microscopy image"), file)
    await user.type(screen.getByLabelText("Case ID"), "CASE-042")
    if (ecd) {
        await user.type(screen.getByLabelText("ECD (cells/mm²)"), ecd)
    }
    await user.click(screen.getByRole("button", { name: "Analyse" }))
    return user
}

function moduleCard(title: string) {
    return screen.getByRole("region", { name: title })
}

beforeEach(() => {
    vi.mocked(uploadImage).mockReset().mockResolvedValue({
        imageId: "img-1", caseId: "CASE-042", contentType: "image/jpeg", sizeBytes: 10, width: 1296, height: 972,
    })
    vi.mocked(analyzeCornea).mockReset()
})

describe("AnalysisPage", () => {
    it("uploads the image, analyses it by id and shows each module's results", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis()

        expect(await screen.findByRole("heading", { name: /Results for case CASE-042/ })).toBeInTheDocument()
        expect(uploadImage).toHaveBeenCalledWith("CASE-042", expect.any(File), expect.any(Function))
        expect(analyzeCornea).toHaveBeenCalledWith({ caseId: "CASE-042", imageId: "img-1", ecd: 2400 })
        expect(screen.getByText("Partially completed")).toBeInTheDocument()
        expect(screen.getByText(/Image accepted as a specular microscopy image/)).toHaveTextContent(
            "Image quality and cell detail were not assessed automatically.",
        )

        const cellular = within(moduleCard("Cellular analysis"))
        expect(cellular.getByText("2,488", { exact: false })).toHaveTextContent("2,488cells/mm²")
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
        expect(grade.queryByRole("meter")).not.toBeInTheDocument()
    })

    it("sends no ECD when the field is blank and shows that manual grading is required", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(REVIEW_REQUIRED)
        renderApp("/analysis", makeAuth({ user: makeUser("NURSE") }))

        await runAnalysis({ ecd: "" })

        const grade = within(await screen.findByRole("region", { name: "Cornea grade" }))
        expect(analyzeCornea).toHaveBeenLastCalledWith({ caseId: "CASE-042", imageId: "img-1", ecd: null })
        expect(grade.getByText("Manual grading required")).toBeInTheDocument()
        expect(within(moduleCard("Cellular analysis")).getByText("This module is not available yet.")).toBeInTheDocument()
    })

    it("shows a non-corneal rejection on the image field and uploads the replacement on retry", async () => {
        vi.mocked(analyzeCornea).mockRejectedValueOnce(new ApiError(
            422,
            "Upload a specular microscopy image showing corneal endothelial cells.",
            { image: "Upload a specular microscopy image showing corneal endothelial cells." },
            "INVALID_IMAGE_DOMAIN",
        ))
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await runAnalysis({ file: jpeg("house.jpg") })

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Upload a specular microscopy image showing corneal endothelial cells. Choose a different image and try again.",
        )
        expect(screen.queryByRole("heading", { name: /Results for case/ })).not.toBeInTheDocument()

        vi.mocked(analyzeCornea).mockResolvedValueOnce(RESPONSE)
        await user.upload(screen.getByLabelText("Specular microscopy image"), jpeg("endothelium.jpg"))
        await user.click(screen.getByRole("button", { name: "Analyse" }))

        expect(await screen.findByRole("heading", { name: /Results for case CASE-042/ })).toBeInTheDocument()
        expect(uploadImage).toHaveBeenCalledTimes(2)
    })

    it("reuses the uploaded image when the analysis is run again", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await runAnalysis()
        await screen.findByRole("heading", { name: /Results for case CASE-042/ })
        await user.click(screen.getByRole("button", { name: "Analyse" }))

        await vi.waitFor(() => expect(analyzeCornea).toHaveBeenCalledTimes(2))
        expect(uploadImage).toHaveBeenCalledTimes(1)
    })

    it("rejects a misnamed non-image file before uploading", async () => {
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()

        await user.upload(
            await screen.findByLabelText("Specular microscopy image"),
            new File(["just text"], "scan.png", { type: "image/png" }),
        )

        expect(await screen.findByRole("alert")).toHaveTextContent("Choose a JPEG or PNG image.")
        expect(uploadImage).not.toHaveBeenCalled()
    })

    it("rejects an out-of-range ECD without uploading or analysing", async () => {
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis({ ecd: "7000" })

        expect(await screen.findByRole("alert")).toHaveTextContent(/at most 6000/)
        expect(uploadImage).not.toHaveBeenCalled()
        expect(analyzeCornea).not.toHaveBeenCalled()
    })

    it("reports a failed module without exposing its internal error", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("NURSE") }))

        await runAnalysis()

        const disease = within(await screen.findByRole("region", { name: "Disease screening" }))
        expect(disease.getByText("Failed")).toBeInTheDocument()
        expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    })

    it("is not available to roles without the analysis permission", async () => {
        renderApp("/analysis", makeAuth({ user: makeUser("SUPPORT_STAFF") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
        expect(screen.queryByLabelText("Specular microscopy image")).not.toBeInTheDocument()
    })

    it("is linked from the clinical dashboard and navigation", async () => {
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("DOCTOR") }))

        expect(await screen.findByRole("link", { name: /Open workspace/ })).toHaveAttribute("href", "/analysis")
        expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("AI analysis")
    })
})
