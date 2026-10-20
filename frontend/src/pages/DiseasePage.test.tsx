import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { uploadImage } from "@/api/analysis"
import { analyzeDisease, readCellChekReport, type DiseaseAnalyzeResponse } from "@/api/disease"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    listModuleRuns: vi.fn().mockResolvedValue({ items: [], nextBefore: null }),
}))
vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    uploadImage: vi.fn(),
}))
vi.mock(import("@/api/disease"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeDisease: vi.fn(),
    readCellChekReport: vi.fn(),
}))

const QUALITY = {
    rating: "OK", focus: 43.6, focusLowLimit: 25.2, darkFraction: 0, saturatedFraction: 0.001, contrast: 45.9,
    unusualDistance: 0.155, unusualWarnAbove: 0.17, unusualRejectAbove: 0.188,
}

const FECD_SHAP = {
    baseline: 0.13,
    prediction: 0.82,
    values: [
        { input: "ECD_CD_cells_per_mm2", value: 1667, imputed: false, contribution: 0.69 },
        { input: "SD", value: 180, imputed: false, contribution: 0.01 },
        { input: "CV", value: 30, imputed: false, contribution: 0.003 },
        { input: "HEX_percent", value: 72, imputed: false, contribution: -0.01 },
        { input: "Donor_Age", value: null, imputed: true, contribution: 0 },
    ],
}

const COMPLETED: DiseaseAnalyzeResponse = {
    analysisId: "run-1",
    caseId: "12656R",
    status: "completed",
    message: "Research tool, not a medical diagnosis.",
    imageValidation: { domainStatus: "VALID_CORNEAL_IMAGE", qualityAssessed: true, width: 1296, height: 972, format: "JPEG" },
    inputCheck: { passed: true, forced: false, errors: [], warnings: [
        { code: "VALUE_MISSING", field: "Donor_Age", message: "Donor age not recorded; the training median is used." },
    ] },
    imageQuality: QUALITY,
    method: "densenet121_image_numbers_fusion_v2",
    diseases: [
        { code: "FECD", label: "Fuchs endothelial corneal dystrophy (FECD)", probability: 0.82, threshold: 0.23, detected: true, gradcamPng: "iVBORw0KGgo=", gradcamFocus: { region: "lower right", coverage: 0.09 }, shap: FECD_SHAP },
        { code: "Guttata", label: "Guttata", probability: 0.12, threshold: 0.44, detected: false, gradcamPng: null, gradcamFocus: null, shap: FECD_SHAP },
        { code: "Folds", label: "Descemet folds", probability: 0.3, threshold: 0.49, detected: false, gradcamPng: null, gradcamFocus: null, shap: FECD_SHAP },
        { code: "PolyPleo", label: "Polymegathism / pleomorphism", probability: 0.2, threshold: 0.44, detected: false, gradcamPng: null, gradcamFocus: null, shap: FECD_SHAP },
        { code: "LowCD", label: "Low cell density", probability: 0.1, threshold: 0.47, detected: false, gradcamPng: null, gradcamFocus: null, shap: FECD_SHAP },
    ],
    detected: ["FECD"],
    normal: false,
    severity: [{ group: "FECDgroup", label: "FECD group", diseases: ["FECD"], grade: "Mod/Sev", probability: 0.7, threshold: 0.57, method: "model", shap: { ...FECD_SHAP, baseline: 0.5, prediction: 0.7 } }],
    overallSeverity: "Mod/Sev",
    severityProbabilities: { FECDgroup: 0.7, Folds: 0.2, Guttata: 0.3 },
    measurementsUsed: { ECD_CD_cells_per_mm2: 1667, ECD_Deficit: 833, SD: 180, CV: 30, HEX_percent: 72, Donor_Age: null },
    measurementsNotRecorded: ["Donor_Age"],
    reliable: true,
}

const CHECKS_FAILED: DiseaseAnalyzeResponse = {
    ...COMPLETED,
    status: "input_check_failed",
    message: "The inputs did not pass the checks.",
    inputCheck: {
        passed: false, forced: false,
        errors: [{ code: "VALUE_NOT_POSSIBLE", field: "ECD_CD_cells_per_mm2", message: "ECD = 0: zero or negative is impossible. Leave it blank if unknown." }],
        warnings: [],
    },
    diseases: null, detected: null, severity: null, overallSeverity: null, reliable: null,
}

function jpeg() {
    return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])], "endothelium.jpg", { type: "image/jpeg" })
}

async function fillAndAnalyse(values: Record<string, string>) {
    const user = userEvent.setup()
    await user.upload(await screen.findByLabelText("Specular microscopy image"), jpeg())
    await user.type(screen.getByLabelText("Tissue ID"), "12656R")
    for (const [label, value] of Object.entries(values)) {
        await user.type(screen.getByLabelText(label), value)
    }
    await user.click(screen.getByRole("button", { name: "Analyse" }))
    return user
}

beforeEach(() => {
    vi.mocked(uploadImage).mockReset().mockResolvedValue({
        imageId: "img-1", caseId: "12656R", contentType: "image/jpeg", sizeBytes: 10, width: 1296, height: 972,
    })
    vi.mocked(analyzeDisease).mockReset()
    vi.mocked(readCellChekReport).mockReset()
})

describe("DiseasePage", () => {
    it("is in the navigation for clinical roles", async () => {
        renderApp("/disease", makeAuth({ user: makeUser("NURSE") }))
        expect(await screen.findByRole("link", { name: /Disease screening/ })).toHaveAttribute("href", "/disease")
        expect(screen.getByText(/not a medical diagnosis/)).toBeInTheDocument()
    })

    it("sends blank values as null, never 0, and shows the report with Grad-CAM", async () => {
        vi.mocked(analyzeDisease).mockResolvedValue(COMPLETED)
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndAnalyse({ "ECD (cells/mm²)": "1667", "SD of cell area (µm²)": "180", "Coefficient of variation (%)": "30", "Hexagonality (%)": "72" })

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        expect(analyzeDisease).toHaveBeenCalledWith({
            caseId: "12656R", imageId: "img-1", force: false,
            measurements: { ECD_CD_cells_per_mm2: 1667, SD: 180, CV: 30, HEX_percent: 72, Donor_Age: null },
        })
        const findings = within(screen.getByRole("region", { name: "Disease findings" }))
        expect(findings.getAllByText("Found")).toHaveLength(1)
        expect(findings.getAllByText("Not found")).toHaveLength(4)
        const severity = within(screen.getByRole("region", { name: "Severity" }))
        expect(severity.getByText("Overall severity").parentElement).toHaveTextContent("Mod/Sev")
        expect(screen.getByRole("img", { name: /Grad-CAM heat map for Fuchs/ })).toHaveAttribute("src", "data:image/png;base64,iVBORw0KGgo=")
        expect(screen.getByText("Donor age not recorded; the training median is used.")).toBeInTheDocument()
        expect(within(screen.getByRole("region", { name: "Inputs used" })).queryByText(/deficit/i)).not.toBeInTheDocument()
    })

    it("explains each Grad-CAM map and can show the original image instead", async () => {
        vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:original", revokeObjectURL: () => {} }))
        vi.mocked(analyzeDisease).mockResolvedValue(COMPLETED)
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await fillAndAnalyse({})

        const gradcam = within(await screen.findByRole("region", { name: "Grad-CAM explanations" }))
        expect(gradcam.getByText("How to read these maps")).toBeInTheDocument()
        expect(gradcam.getByText(/Strongest in the/)).toHaveTextContent(
            "Strongest in the lower right of the image; 9% of the image highlighted (focused).")
        expect(gradcam.getByText(/Guttae: dark, round or oval spots/)).toBeInTheDocument()
        expect(gradcam.getByText(/test AUC numbers only 0.87, image only 0.83/)).toBeInTheDocument()

        await user.click(gradcam.getByRole("button", { name: "Show original" }))
        expect(gradcam.getByRole("img", { name: /Original image/ })).toHaveAttribute("src", "blob:original")
        await user.click(gradcam.getByRole("button", { name: "Show heat map" }))
        expect(gradcam.getByRole("img", { name: /Grad-CAM heat map/ })).toBeInTheDocument()
        vi.unstubAllGlobals()
    })

    it("shows how each CellChek value moved the probability (SHAP)", async () => {
        vi.mocked(analyzeDisease).mockResolvedValue(COMPLETED)
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await fillAndAnalyse({})

        const shap = within(await screen.findByRole("region", { name: /How the CellChek values affected the result/ }))
        expect(shap.getByRole("button", { name: /Fuchs/ })).toHaveAttribute("aria-pressed", "true")
        expect(shap.getByText(/this image with typical values/)).toHaveTextContent("13%")
        expect(shap.getByText(/this image with typical values/)).toHaveTextContent("82%")
        const ecdRow = shap.getByRole("row", { name: /ECD/ })
        expect(ecdRow).toHaveTextContent("1,667 cells/mm²")
        expect(ecdRow).toHaveTextContent("+69")
        expect(shap.getByRole("row", { name: /Coefficient of variation/ })).toHaveTextContent("+<1")
        expect(shap.getByRole("row", { name: /Hexagonality/ })).toHaveTextContent("−1")
        expect(shap.getByRole("row", { name: /Donor age/ })).toHaveTextContent("not recorded (median used)")

        await user.click(shap.getByRole("button", { name: "Severity: FECD group" }))
        expect(shap.getByText(/this image with typical values/)).toHaveTextContent("50%")
        expect(shap.getByRole("button", { name: "Guttata" })).toBeInTheDocument()
    })

    it("shows failed input checks and can run anyway with force", async () => {
        vi.mocked(analyzeDisease).mockResolvedValueOnce(CHECKS_FAILED)
            .mockResolvedValueOnce({ ...COMPLETED, reliable: false, inputCheck: { ...CHECKS_FAILED.inputCheck!, forced: true } })
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))

        const user = await fillAndAnalyse({ "ECD (cells/mm²)": "0" })

        expect(await screen.findByText(/zero or negative is impossible/)).toBeInTheDocument()
        expect(screen.queryByRole("heading", { name: /Results for case/ })).not.toBeInTheDocument()
        await user.click(screen.getByRole("button", { name: "Run anyway" }))

        expect(await screen.findByText("Forced — not reliable")).toBeInTheDocument()
        expect(analyzeDisease).toHaveBeenLastCalledWith(expect.objectContaining({ force: true, imageId: "img-1" }))
        expect(uploadImage).toHaveBeenCalledTimes(1)
    })

    it("shows a non-corneal image rejection at the image field", async () => {
        vi.mocked(analyzeDisease).mockRejectedValue(new ApiError(422, "Upload a specular microscopy image showing corneal endothelial cells.", { image: "x" }, "INVALID_IMAGE_DOMAIN"))
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndAnalyse({})

        expect(await screen.findByText(/Choose a different image and try again/)).toBeInTheDocument()
    })

    it("fills the values from a CellChek report for the clinician to check", async () => {
        vi.mocked(readCellChekReport).mockResolvedValue({
            source: "image",
            values: { ECD_CD_cells_per_mm2: 2016, SD: 175, CV: 35, HEX_percent: 48, Donor_Age: null },
            notFound: ["Donor_Age"],
            tissueId: "NEB-2020-09-12673 L",
            eye: "OS",
            totalCells: 124,
            totalAreaUm2: 61468,
            warnings: [{ code: "REPORT_LOW_CONFIDENCE", field: "CV", message: "CV (35) was hard to read; check it against the report." }],
        })
        vi.mocked(analyzeDisease).mockResolvedValue(COMPLETED)
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))
        const user = userEvent.setup()

        await user.upload(await screen.findByLabelText(/Fill from CellChek report/), new File(["x"], "report.jpg", { type: "image/jpeg" }))

        expect(await screen.findByText(/Filled 4 of 5 values from the report/)).toHaveTextContent("NEB-2020-09-12673 L (OS)")
        expect(screen.getByLabelText(/^ECD/)).toHaveValue("2016")
        expect(screen.getByLabelText(/^Hexagonality/)).toHaveValue("48")
        expect(screen.getByLabelText(/^Donor age/)).toHaveValue("")
        expect(screen.getAllByText("From report")).toHaveLength(4)
        expect(screen.getByText(/Not found in the report/)).toHaveTextContent("Donor age")
        expect(screen.getByText("CV (35) was hard to read; check it against the report.")).toBeInTheDocument()

        await user.click(screen.getByRole("button", { name: "Use NEB-2020-09-12673 L as case ID" }))
        expect(screen.getByLabelText("Case ID")).toHaveValue("NEB-2020-09-12673 L")

        await user.clear(screen.getByLabelText(/^SD of cell area/))
        await user.type(screen.getByLabelText(/^SD of cell area/), "176")
        expect(screen.getAllByText("From report")).toHaveLength(3)

        await user.upload(screen.getByLabelText("Specular microscopy image"), jpeg())
        await user.click(screen.getByRole("button", { name: "Analyse" }))
        await screen.findByRole("heading", { name: /Results for case/ })
        expect(analyzeDisease).toHaveBeenCalledWith(expect.objectContaining({
            caseId: "NEB-2020-09-12673 L",
            measurements: { ECD_CD_cells_per_mm2: 2016, SD: 176, CV: 35, HEX_percent: 48, Donor_Age: null },
        }))
    })

    it("asks for manual entry when the report cannot be read", async () => {
        vi.mocked(readCellChekReport).mockRejectedValue(new ApiError(422, "No CellChek values could be read from this file. Enter them by hand.", {}, "REPORT_NO_VALUES"))
        renderApp("/disease", makeAuth({ user: makeUser("NURSE") }))
        const user = userEvent.setup()

        await user.upload(await screen.findByLabelText(/Fill from CellChek report/), new File(["x"], "blank.png", { type: "image/png" }))

        expect(await screen.findByText(/No CellChek values could be read/)).toBeInTheDocument()
        expect(screen.getByLabelText(/^ECD/)).toHaveValue("")
    })

    it("flags a value that is not a number before sending", async () => {
        renderApp("/disease", makeAuth({ user: makeUser("DOCTOR") }))
        await fillAndAnalyse({ "Donor age (years)": "sixty" })
        expect(await screen.findByText("Donor age must be a number, or blank if unknown.")).toBeInTheDocument()
        expect(analyzeDisease).not.toHaveBeenCalled()
    })
})
