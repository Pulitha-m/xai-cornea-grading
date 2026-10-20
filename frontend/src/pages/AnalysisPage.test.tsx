import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { analyzeCornea, uploadImage, type AnalyzeResponse, type EcdReference } from "@/api/analysis"
import { ApiError } from "@/lib/api-client"
import { FEATURES } from "@/lib/grading-features"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

// Keep the real constants (used by validation); mock only the network calls.
vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listModuleRuns: vi.fn().mockResolvedValue({ items: [], nextBefore: null }),
}))
vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeCornea: vi.fn(),
    uploadImage: vi.fn(),
}))

const GRADING_MESSAGE =
    "Grade from the hybrid model (24 Konan and slit-lamp inputs plus image features). In nested cross-validation it was not better than the ECD rule shown below. Specialist confirmation required."

const ECD_REFERENCE: EcdReference = {
    status: "completed",
    grade: "A",
    method: "ecd_threshold_tree",
    ecdUsed: 2400,
    ecdBand: { lowerExclusive: 2232, upperInclusive: 2497 },
    bandDistribution: { "A+": 0.021, A: 0.894, B: 0.085 },
    bandTrainingTissues: 94,
    reviewRequired: false,
    message: "Grade based on ECD only. Specialist confirmation required.",
}

const NOT_RECORDED = FEATURES.map((f) => f.name).filter((name) => name !== "ECD_CD_cells_per_mm2" && name !== "Stroma_Has_Scar")

const RESPONSE: AnalyzeResponse = {
    analysisId: "run-1",
    caseId: "12656R",
    status: "partial",
    imageValidation: { domainStatus: "VALID_CORNEAL_IMAGE", qualityAssessed: false, width: 1296, height: 972, format: "JPEG" },
    cellular: { status: "completed", error: null, cellCount: 312, ecd: 2487.6, coefficientOfVariation: 0.3, hexagonality: 0.7 },
    grading: {
        status: "completed",
        error: null,
        grade: "B",
        method: "hybrid_random_forest_24_resnet50",
        modelProbabilities: { "A+": 0.05, A: 0.32, B: 0.63 },
        featuresNotRecorded: NOT_RECORDED,
        warnings: [],
        ecdReference: ECD_REFERENCE,
        reviewRequired: false,
        message: GRADING_MESSAGE,
    },
    disease: { status: "failed", error: "Traceback: model weights missing", disease: null, severity: null, confidence: null },
    recommendation: { status: "completed", error: null, recommendation: "Suitable for further evaluation", confidence: 0.88 },
}

const NO_ECD: AnalyzeResponse = {
    ...RESPONSE,
    cellular: { status: "not_implemented", error: "Cellular analysis is not implemented yet.", cellCount: null, ecd: null, coefficientOfVariation: null, hexagonality: null },
    grading: {
        ...RESPONSE.grading,
        featuresNotRecorded: FEATURES.map((f) => f.name),
        warnings: [
            { code: "FEATURE_OUTSIDE_TRAINING_RANGE", field: "CV", message: "CV 80 is outside the training range (24–74)." },
            { code: "IMAGE_NOT_TRAINING_SIZE", field: "image", message: "The image is 640 × 480 px; it was resized." },
        ],
        ecdReference: {
            ...ECD_REFERENCE,
            status: "review_required",
            grade: null,
            ecdUsed: null,
            ecdBand: null,
            bandDistribution: null,
            bandTrainingTissues: null,
            reviewRequired: true,
            message: "ECD is required for automated grading. Grade this tissue manually.",
        },
        reviewRequired: true,
    },
}

/** All 24 features as sent by the form: null unless overridden. */
function expectedFeatures(overrides: Record<string, number | string | null> = {}) {
    return { ...Object.fromEntries(FEATURES.map((f) => [f.name, null])), ...overrides }
}

const JPEG_BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])

function jpeg(name = "endothelium.jpg") {
    return new File([JPEG_BYTES], name, { type: "image/jpeg" })
}

type User = ReturnType<typeof userEvent.setup>

async function runAnalysis({
    ecd = "2400",
    scar = "No",
    file = jpeg(),
    fill,
}: { ecd?: string; scar?: string; file?: File; fill?: (user: User) => Promise<void> } = {}) {
    const user = userEvent.setup()
    await user.upload(await screen.findByLabelText("Specular microscopy image"), file)
    await user.type(screen.getByLabelText("Tissue ID"), "12656R")
    if (ecd) {
        await user.type(screen.getByLabelText("ECD (cells/mm²)"), ecd)
    }
    if (scar) {
        await user.selectOptions(within(featureGroup("Slit-lamp: stroma")).getByLabelText("Scar"), scar)
    }
    await fill?.(user)
    await user.click(screen.getByRole("button", { name: "Analyse" }))
    return user
}

function featureGroup(title: string) {
    return screen.getByRole("group", { name: title })
}

function moduleCard(title: string) {
    return screen.getByRole("region", { name: title })
}

beforeEach(() => {
    vi.mocked(uploadImage).mockReset().mockResolvedValue({
        imageId: "img-1", caseId: "12656R", contentType: "image/jpeg", sizeBytes: 10, width: 1296, height: 972,
    })
    vi.mocked(analyzeCornea).mockReset()
})

describe("AnalysisPage", () => {
    it("uploads the image, analyses it by id and shows each module's results", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis()

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        expect(uploadImage).toHaveBeenCalledWith("12656R", expect.any(File), expect.any(Function))
        expect(analyzeCornea).toHaveBeenCalledWith({
            caseId: "12656R",
            imageId: "img-1",
            clinicalFeatures: expectedFeatures({ ECD_CD_cells_per_mm2: 2400, Stroma_Has_Scar: 0 }),
        })
        expect(screen.getByText("Partially completed")).toBeInTheDocument()
        expect(screen.getByText(/Image accepted as a specular microscopy image/)).toHaveTextContent(
            "Image quality and cell detail were not assessed automatically.",
        )

        const cellular = within(moduleCard("Cellular analysis"))
        expect(cellular.getByText("2,488", { exact: false })).toHaveTextContent("2,488cells/mm²")
        expect(within(moduleCard("Recommendation")).getByText("Suitable for further evaluation")).toBeInTheDocument()
    })

    it("shows the model grade with uncalibrated tree votes and the ECD rule as a reference", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis()

        const grade = within(await screen.findByRole("region", { name: "Cornea grade" }))
        expect(grade.getByText("Predicted grade").parentElement).toHaveTextContent(/^Predicted gradeB$/)
        expect(grade.getByText("Inputs recorded").parentElement).toHaveTextContent(/^Inputs recorded2 of 24$/)
        expect(grade.getByText("Not calibrated — not a confidence")).toBeInTheDocument()
        expect(grade.getByText("63%")).toBeInTheDocument()
        expect(grade.getByText("ECD rule grade").parentElement).toHaveTextContent(/^ECD rule gradeA$/)
        expect(grade.getByText("2,232 < ECD ≤ 2,497")).toBeInTheDocument()
        expect(grade.getByText(/94 training tissues in this band/)).toBeInTheDocument()
        expect(grade.getByText("22 inputs not recorded")).toBeInTheDocument()
        expect(grade.queryByRole("meter")).not.toBeInTheDocument()
    })

    it("sends null for every input left as not recorded and shows the server's warnings", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(NO_ECD)
        renderApp("/analysis", makeAuth({ user: makeUser("NURSE") }))

        await runAnalysis({ ecd: "", scar: "" })

        const grade = within(await screen.findByRole("region", { name: "Cornea grade" }))
        expect(analyzeCornea).toHaveBeenLastCalledWith({ caseId: "12656R", imageId: "img-1", clinicalFeatures: expectedFeatures() })
        expect(grade.getByRole("alert")).toHaveTextContent("CV 80 is outside the training range")
        expect(grade.getByRole("alert")).toHaveTextContent("The image is 640 × 480 px; it was resized.")
        expect(grade.getByText("ECD is required for automated grading. Grade this tissue manually.")).toBeInTheDocument()
        expect(within(moduleCard("Cellular analysis")).getByText("This module is not available yet.")).toBeInTheDocument()
    })

    it("sends slit-lamp categories and binary findings as recorded", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis({
            fill: async (user) => {
                const descemet = within(featureGroup("Slit-lamp: Descemet's membrane"))
                await user.selectOptions(descemet.getByLabelText("Folds"), "Yes")
                await user.selectOptions(descemet.getByLabelText("Fold severity"), "Very mild")
                await user.type(screen.getByLabelText("Hexagonality (%)"), "55")
            },
        })

        await screen.findByRole("heading", { name: /Results for case 12656R/ })
        expect(analyzeCornea).toHaveBeenCalledWith(expect.objectContaining({
            clinicalFeatures: expectedFeatures({
                ECD_CD_cells_per_mm2: 2400,
                HEX_percent: 55,
                Stroma_Has_Scar: 0,
                Descemet_Has_Folds: 1,
                Descemet_Fold_Severity: "Very mild",
            }),
        }))
    })

    it("shows server feature errors at their fields until the field is edited", async () => {
        vi.mocked(analyzeCornea).mockRejectedValueOnce(new ApiError(
            422,
            "Hexagonality must be at most 100.",
            { HEX_percent: "Hexagonality must be at most 100." },
            "FEATURE_OUT_OF_RANGE",
        ))
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await runAnalysis()

        const hex = screen.getByLabelText("Hexagonality (%)")
        await vi.waitFor(() => expect(hex).toHaveAttribute("aria-invalid", "true"))
        expect(hex).toHaveAccessibleDescription("Hexagonality must be at most 100.")
        expect(screen.getByText("Correct the highlighted clinical feature and try again.")).toBeInTheDocument()

        await user.type(hex, "5")
        expect(hex).toHaveAttribute("aria-invalid", "false")
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

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        expect(uploadImage).toHaveBeenCalledTimes(2)
    })

    it("reuses the uploaded image when the analysis is run again", async () => {
        vi.mocked(analyzeCornea).mockResolvedValue(RESPONSE)
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await runAnalysis()
        await screen.findByRole("heading", { name: /Results for case 12656R/ })
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

    it("rejects impossible clinical values without uploading or analysing", async () => {
        renderApp("/analysis", makeAuth({ user: makeUser("DOCTOR") }))

        await runAnalysis({ ecd: "-5", fill: (user) => user.type(screen.getByLabelText("Hexagonality (%)"), "120") })

        expect(screen.getByLabelText("ECD (cells/mm²)")).toHaveAccessibleDescription("ECD must be greater than 0.")
        expect(screen.getByLabelText("Hexagonality (%)")).toHaveAccessibleDescription(/at most 100/)
        expect(screen.getByText("Correct the 2 highlighted clinical features and try again.")).toBeInTheDocument()
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
