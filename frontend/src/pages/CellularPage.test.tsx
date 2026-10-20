import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { uploadImage } from "@/api/analysis"
import { analyzeCellular, type CellularAnalyzeResponse } from "@/api/cellular"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/analysis"), async (importOriginal) => ({
    ...(await importOriginal()),
    uploadImage: vi.fn(),
}))
vi.mock(import("@/api/cellular"), async (importOriginal) => ({
    ...(await importOriginal()),
    analyzeCellular: vi.fn(),
}))

const COMPLETED: CellularAnalyzeResponse = {
    analysisId: "run-1",
    caseId: "12656R",
    status: "completed",
    message: "Research tool for a specialist, not a clinical measurement.",
    imageValidation: { domainStatus: "VALID_CORNEAL_IMAGE", qualityAssessed: true, width: 1296, height: 972, format: "JPEG" },
    method: "roi_efficientnet_b0_stardist_onnx_v1",
    umPerPx: 0.796,
    validatedImageSize: true,
    biomarkers: {
        cellCount: 1421, ecd: 2824.48, meanAreaUm2: 354.04, sdAreaUm2: 97.42, coefficientOfVariation: 27.52,
        hexagonality: 64.59, cellsWithSides: 1087, meanCompactness: 0.887, sdCompactness: 0.035, cvCompactness: 3.97,
        areaPercentilesUm2: { p5: 214.2, p25: 288.9, p50: 347.2, p75: 406.8, p95: 524.6 },
        sideDistributionPct: { "<=4": 0.9, "5": 20.2, "6": 64.59, "7": 13.9, ">=8": 0.4 },
        flaggedCells: 1,
    },
    roi: { method: "cnn", shareOfImage: 0.72, shareOfLitArea: 0.78, qualityScore: 0.78 },
    qualityFlags: [],
    reliable: true,
    uncertainty: { method: "95 % CI", ecdCi95: [2785.0, 2865.4], cvCi95: [25.97, 29.09], hexCi95: [61.3, 67.7] },
    evidence: { mostExtremeCellsPct: 5, theirShareOfAreaVariancePct: 36.5 },
    reliability: { rule: "rule", green: 1351, yellow: 64, red: 6, medianConfidence: 0.904 },
    images: { overlayJpeg: "/9j/overlay", reliabilityJpeg: "/9j/reliability", cvEvidenceJpeg: "/9j/cv" },
    seconds: 7.4,
}

const NOT_RELIABLE: CellularAnalyzeResponse = {
    ...COMPLETED,
    reliable: false,
    biomarkers: { ...COMPLETED.biomarkers, cellCount: 12 },
    qualityFlags: [
        { level: "error", code: "too_few_cells", message: "only 12 complete cells (< 30): biomarkers not reliable" },
        { level: "warning", code: "small_roi", message: "ROI keeps only 20 % of the lit area: image largely of poor quality" },
    ],
}

function jpeg() {
    return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])], "endothelium.jpg", { type: "image/jpeg" })
}

async function uploadAndAnalyse() {
    const user = userEvent.setup()
    await user.upload(await screen.findByLabelText("Specular microscopy image"), jpeg())
    await user.type(screen.getByLabelText("Tissue ID"), "12656R")
    await user.click(screen.getByRole("button", { name: "Analyse" }))
    return user
}

beforeEach(() => {
    vi.mocked(uploadImage).mockReset().mockResolvedValue({
        imageId: "img-1", caseId: "12656R", contentType: "image/jpeg", sizeBytes: 10, width: 1296, height: 972,
    })
    vi.mocked(analyzeCellular).mockReset()
})

describe("CellularPage", () => {
    it("is in the navigation for clinical roles", async () => {
        renderApp("/cellular", makeAuth({ user: makeUser("NURSE") }))
        expect(await screen.findByRole("link", { name: /Cellular analysis/ })).toHaveAttribute("href", "/cellular")
        expect(screen.getAllByText(/not a clinical measurement/).length).toBeGreaterThan(0)
    })

    it("is not offered to support staff", async () => {
        renderApp("/support/dashboard", makeAuth({ user: makeUser("SUPPORT_STAFF") }))
        await screen.findByRole("navigation")
        expect(screen.queryByRole("link", { name: /Cellular analysis/ })).not.toBeInTheDocument()
    })

    it("uploads the image, analyses it by id and shows the report with intervals and reliability", async () => {
        vi.mocked(analyzeCellular).mockResolvedValue(COMPLETED)
        renderApp("/cellular", makeAuth({ user: makeUser("DOCTOR") }))

        await uploadAndAnalyse()

        expect(await screen.findByRole("heading", { name: /Results for case 12656R/ })).toBeInTheDocument()
        expect(analyzeCellular).toHaveBeenCalledWith({ caseId: "12656R", imageId: "img-1" })
        expect(screen.getByText("Completed")).toBeInTheDocument()

        const biomarkers = within(screen.getByRole("region", { name: "Biomarkers" }))
        expect(biomarkers.getByText("Endothelial cell density").parentElement).toHaveTextContent("2,824")
        expect(biomarkers.getByText("95% CI 2,785 – 2,865")).toBeInTheDocument()
        expect(biomarkers.getByText("Coefficient of variation").parentElement).toHaveTextContent("27.5%")
        expect(biomarkers.getByText("95% CI 26.0 – 29.1")).toBeInTheDocument()
        expect(biomarkers.getByText("Hexagonality").parentElement).toHaveTextContent("64.6%")

        const reliability = within(screen.getByRole("region", { name: "Cell reliability" }))
        expect(reliability.getByText("Yellow", { selector: "dt" }).parentElement).toHaveTextContent("64")
        expect(reliability.getByText("Red", { selector: "dt" }).parentElement).toHaveTextContent("6")
    })

    it("switches between the overlays", async () => {
        vi.mocked(analyzeCellular).mockResolvedValue(COMPLETED)
        renderApp("/cellular", makeAuth({ user: makeUser("DOCTOR") }))
        const user = await uploadAndAnalyse()

        const overlays = within(await screen.findByRole("region", { name: "Overlays" }))
        expect(overlays.getByRole("img")).toHaveAttribute("src", "data:image/jpeg;base64,/9j/overlay")
        await user.click(overlays.getByRole("button", { name: "Reliability" }))
        expect(overlays.getByRole("img")).toHaveAttribute("src", "data:image/jpeg;base64,/9j/reliability")
        expect(overlays.getByRole("button", { name: "Reliability" })).toHaveAttribute("aria-pressed", "true")
        await user.click(overlays.getByRole("button", { name: "Cell area (CV)" }))
        expect(overlays.getByRole("img")).toHaveAttribute("src", "data:image/jpeg;base64,/9j/cv")
    })

    it("marks a result with an error flag as not reliable and lists the flags", async () => {
        vi.mocked(analyzeCellular).mockResolvedValue(NOT_RELIABLE)
        renderApp("/cellular", makeAuth({ user: makeUser("DOCTOR") }))

        await uploadAndAnalyse()

        expect(await screen.findByText("Not reliable")).toBeInTheDocument()
        expect(screen.getByText("The biomarkers are not reliable:")).toBeInTheDocument()
        expect(screen.getByText(/only 12 complete cells/)).toBeInTheDocument()
        expect(screen.getByText(/ROI keeps only 20 %/)).toBeInTheDocument()
    })

    it("shows a non-corneal image rejection at the image field", async () => {
        vi.mocked(analyzeCellular).mockRejectedValue(new ApiError(422, "Upload a specular microscopy image showing corneal endothelial cells.", { image: "x" }, "INVALID_IMAGE_DOMAIN"))
        renderApp("/cellular", makeAuth({ user: makeUser("DOCTOR") }))

        await uploadAndAnalyse()

        expect(await screen.findByText(/Choose a different image and try again/)).toBeInTheDocument()
        expect(screen.queryByRole("heading", { name: /Results for case/ })).not.toBeInTheDocument()
    })
})
