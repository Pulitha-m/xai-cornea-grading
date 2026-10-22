import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { uploadImage } from "@/api/analysis"
import { analyzeGrading, type GradingAnalyzeResponse } from "@/api/grading"
import { ApiError } from "@/lib/api-client"
import { FEATURES } from "@/lib/grading-features"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listModuleRuns: vi.fn().mockResolvedValue({ items: [], nextBefore: null }),
}))
vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    uploadImage: vi.fn(),
}))
vi.mock(import("@/api/grading"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeGrading: vi.fn(),
}))

const FEATURES_USED = { ...Object.fromEntries(FEATURES.map((f) => [f.name, null])), ECD_CD_cells_per_mm2: 2400, Stroma_Has_Scar: 1 }

const COMPLETED: GradingAnalyzeResponse = {
    analysisId: "run-1",
    caseId: "12656R",
    status: "completed",
    imageValidation: { domainStatus: "VALID_CORNEAL_IMAGE", qualityAssessed: false, width: 1296, height: 972, format: "JPEG" },
    grade: "B",
    method: "hybrid_random_forest_24_resnet50",
    modelProbabilities: { "A+": 0.05, A: 0.32, B: 0.63 },
    featuresUsed: FEATURES_USED,
    featuresNotRecorded: FEATURES.map((f) => f.name).filter((n) => n !== "ECD_CD_cells_per_mm2" && n !== "Stroma_Has_Scar"),
    warnings: [],
    ecdReference: {
        status: "completed", grade: "A", method: "ecd_threshold_tree", ecdUsed: 2400,
        ecdBand: { lowerExclusive: 2232, upperInclusive: 2497 }, bandDistribution: { "A+": 0.021, A: 0.894, B: 0.085 },
        bandTrainingTissues: 94, reviewRequired: false, message: "Grade based on ECD only.",
    },
    reviewRequired: false,
    message: "Grade from the hybrid model. Specialist confirmation required.",
    explanation: {
        method: "tree_shap_path_dependent",
        explainedGrade: "B",
        baseline: 0.14,
        prediction: 0.63,
        features: [
            { name: "ECD_CD_cells_per_mm2", value: 2400, contribution: 0.31 },
            { name: "Stroma_Has_Scar", value: 1, contribution: 0.12 },
            ...FEATURES.map((f) => f.name).filter((n) => n !== "ECD_CD_cells_per_mm2" && n !== "Stroma_Has_Scar")
                .map((name, i) => ({ name, value: null, contribution: i === 0 ? -0.02 : 0.001 })),
        ],
        imageContribution: 0.05,
        imageMap: {
            method: "shap_weighted_layer4_map", supportingPng: "iVBORw0KGgo=", opposingPng: null,
            supportingTotal: 0.06, opposingTotal: -0.01, localisedShare: 0.95,
        },
        message: "Contributions explain the model, not the cornea.",
    },
}

function jpeg() {
    return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])], "endothelium.jpg", { type: "image/jpeg" })
}

async function fillAndGrade(ecd: string) {
    const user = userEvent.setup()
    await user.upload(await screen.findByLabelText("Specular microscopy image"), jpeg())
    await user.type(screen.getByLabelText("Tissue ID"), "12656R")
    if (ecd) await user.type(screen.getByLabelText("ECD (cells/mm²)"), ecd)
    await user.click(screen.getByRole("button", { name: "Grade" }))
    return user
}

beforeEach(() => {
    vi.mocked(uploadImage).mockReset().mockResolvedValue({
        imageId: "img-1", caseId: "12656R", contentType: "image/jpeg", sizeBytes: 10, width: 1296, height: 972,
    })
    vi.mocked(analyzeGrading).mockReset()
})

describe("GradingPage", () => {
    it("is in the navigation for clinical roles", async () => {
        renderApp("/grading", makeAuth({ user: makeUser("NURSE") }))
        expect(await screen.findByRole("link", { name: /Cornea grading/ })).toHaveAttribute("href", "/grading")
        expect(screen.getByRole("heading", { name: "Cornea grading", level: 1 })).toBeInTheDocument()
    })

    it("sends all 24 features with blanks as null and shows the grade, votes and what drove it in words", async () => {
        vi.mocked(analyzeGrading).mockResolvedValue(COMPLETED)
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndGrade("2400")

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        const sent = vi.mocked(analyzeGrading).mock.calls[0][0]
        expect(sent).toMatchObject({ caseId: "12656R", imageId: "img-1" })
        expect(Object.keys(sent.clinicalFeatures)).toHaveLength(24)
        expect(sent.clinicalFeatures.ECD_CD_cells_per_mm2).toBe(2400)
        expect(sent.clinicalFeatures.HEX_percent).toBeNull()

        const grade = within(screen.getByRole("region", { name: "Model grade" }))
        expect(grade.getByText("Predicted grade").parentElement).toHaveTextContent("B")
        expect(grade.getByRole("meter", { name: "Share of trees voting B" })).toHaveAttribute("aria-valuenow", "63")
        expect(grade.getByText("Not calibrated — not a confidence")).toBeInTheDocument()

        // The ECD rule is not shown to end users.
        expect(screen.queryByRole("region", { name: "Reference: ECD rule" })).not.toBeInTheDocument()
        expect(screen.queryByText(/ECD rule/)).not.toBeInTheDocument()

        // Effects in words, without percentage points.
        const drivers = within(screen.getByRole("region", { name: "What drove this grade" }))
        expect(drivers.getByLabelText("ECD (2,400 cells/mm²): raised strongly for B")).toBeInTheDocument()
        expect(drivers.getByLabelText("Stroma: Scar (Yes): raised strongly for B")).toBeInTheDocument()
        expect(drivers.getByLabelText("Specular image: raised slightly for B")).toBeInTheDocument()
        expect(drivers.getAllByText("Lowered slightly")).toHaveLength(1)
        expect(drivers.getAllByText("Little effect").length).toBeGreaterThan(0)
        expect(drivers.queryByText(/pts|%/)).not.toBeInTheDocument()

        const where = within(screen.getByRole("region", { name: "Where in the image" }))
        expect(where.getByRole("img", { name: /raised support for b/ })).toHaveAttribute("src", "data:image/png;base64,iVBORw0KGgo=")
        expect(where.getByText("No area")).toBeInTheDocument()
        expect(where.getByText("Raised slightly")).toBeInTheDocument()
        expect(where.queryByText(/pts/)).not.toBeInTheDocument()

        const inputs = within(screen.getByRole("region", { name: "Inputs used" }))
        expect(inputs.getByText("2,400 cells/mm²")).toBeInTheDocument()
        expect(inputs.getByText("Yes")).toBeInTheDocument()
    })

    it("still shows the grade when the explanation could not be computed", async () => {
        vi.mocked(analyzeGrading).mockResolvedValue({ ...COMPLETED, explanation: null })
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))
        await fillAndGrade("2400")

        expect(await screen.findByText(/An explanation of this grade could not be computed/)).toBeInTheDocument()
        expect(screen.getByText("Predicted grade").parentElement).toHaveTextContent("B")
    })

    it("flags review when the server returns warnings", async () => {
        vi.mocked(analyzeGrading).mockResolvedValue({
            ...COMPLETED,
            reviewRequired: true,
            warnings: [{ code: "IMAGE_NOT_TRAINING_SIZE", field: "image", message: "The image was resized." }],
        })
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))
        await fillAndGrade("2400")

        expect(await screen.findByText("Review required")).toBeInTheDocument()
        expect(screen.getByText("The image was resized.")).toBeInTheDocument()
    })

    it("shows a server feature error at its field and reuses the uploaded image on retry", async () => {
        vi.mocked(analyzeGrading)
            .mockRejectedValueOnce(new ApiError(422, "ECD_CD_cells_per_mm2 must be greater than 0.", { ECD_CD_cells_per_mm2: "ECD must be greater than 0." }, "FEATURE_OUT_OF_RANGE"))
            .mockResolvedValueOnce(COMPLETED)
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await fillAndGrade("2400")
        expect(await screen.findByText("ECD must be greater than 0.")).toBeInTheDocument()
        await user.click(screen.getByRole("button", { name: "Grade" }))

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        expect(uploadImage).toHaveBeenCalledTimes(1)
    })

    it("shows a non-corneal image rejection at the image field", async () => {
        vi.mocked(analyzeGrading).mockRejectedValue(new ApiError(422, "Upload a specular microscopy image showing corneal endothelial cells.", { image: "x" }, "INVALID_IMAGE_DOMAIN"))
        renderApp("/grading", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndGrade("")

        expect(await screen.findByText(/Choose a different image and try again/)).toBeInTheDocument()
    })
})
