import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { recommendFollowup, type FollowupResponse } from "@/api/recommendation"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/recommendation"), async (importOriginal) => ({
    ...(await importOriginal()),
    recommendFollowup: vi.fn(),
}))

const RED: FollowupResponse = {
    analysisId: "run-1",
    graftId: "G0001",
    alert: "red",
    nextVisitMonths: 3,
    rulesFired: ["12-month ECD < 750", "cell loss by 12 months >= 40%"],
    actions: ["Consider regraft assessment: ECD projected below 500 within 3 years",
        "Repeat specular microscopy (ECD, CV, HEX) at the next visit"],
    predictedEcd: [
        { months: 24, ecd: 542, low: 485, high: 641 },
        { months: 36, ecd: 380, low: 300, high: 460 },
        { months: 60, ecd: 350, low: 230, high: 470 },
    ],
    bandLevel: "10-90%",
    risk: [
        { outcome: "graft_failure", withinMonths: 12, probability: 0.41 },
        { outcome: "graft_failure", withinMonths: 24, probability: 0.839 },
        { outcome: "low_ecd", withinMonths: 12, probability: 1 },
        { outcome: "low_ecd", withinMonths: 24, probability: 1 },
    ],
    reasons: {
        trajectory: [{ reason: "early cell loss", effectPct: -28.4 }],
        graftFailure: [{ reason: "early cell loss", hazardRatio: 22.52 }],
        lowEcd: [],
    },
    counterfactuals: ["risk would be under 10% with: 12-month ECD 1500 instead of 1000 (risk 8%) [descriptive]"],
    model: "followup-12m-visit",
    modelVersion: "2026-10-20",
    rulesVersion: "placeholder-2026-10-20",
    dataSource: "simulated",
    disclaimer: "Decision support only. Follow-up decisions rest with the treating clinician.",
}

async function fillAndSubmit(options: { skip3m?: boolean; leaveOut?: string } = {}) {
    const user = userEvent.setup()
    const fields: [string, string][] = [
        ["Graft ID", "G0001"], ["Donor age", "60"], ["Donor ECD", "2700"], ["Donor CV", "36"], ["Donor HEX", "56"],
        ["6-month ECD", "1700"], ["6-month CV", "42"], ["6-month HEX", "50"],
        ["12-month ECD", "1000"], ["12-month CV", "46"], ["12-month HEX", "45"],
    ]
    if (!options.skip3m) fields.push(["3-month ECD", "2300"], ["3-month CV", "38"], ["3-month HEX", "54"])
    for (const [label, value] of fields) {
        if (label === options.leaveOut) continue
        await user.type(await screen.findByLabelText(new RegExp(`^${label}`)), value)
    }
    await user.click(screen.getByRole("button", { name: "Get recommendation" }))
    return user
}

beforeEach(() => {
    vi.mocked(recommendFollowup).mockReset()
})

describe("FollowupPage", () => {
    it("is in the navigation for clinical roles and is no longer 'coming soon'", async () => {
        renderApp("/post-transplant", makeAuth({ user: makeUser("NURSE") }))
        expect(await screen.findByRole("link", { name: /Post-transplant follow-up/ })).toHaveAttribute("href", "/post-transplant")
        expect(screen.getByRole("heading", { name: "Post-transplant follow-up", level: 1 })).toBeInTheDocument()
        expect(screen.getAllByText(/Decision support only/).length).toBeGreaterThan(0)
    })

    it("is not offered to support staff", async () => {
        renderApp("/support/dashboard", makeAuth({ user: makeUser("SUPPORT_STAFF") }))
        await screen.findByRole("navigation")
        expect(screen.queryByRole("link", { name: /Post-transplant follow-up/ })).not.toBeInTheDocument()
    })

    it("sends the visits and shows the alert, next visit, predictions, risk and reasons", async () => {
        vi.mocked(recommendFollowup).mockResolvedValue(RED)
        renderApp("/post-transplant", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndSubmit()

        expect(await screen.findByText("Red alert")).toBeInTheDocument()
        expect(screen.getByText("Next visit in 3 months")).toBeInTheDocument()
        expect(recommendFollowup).toHaveBeenCalledWith({
            graftId: "G0001", procedure: "PK", indication: "Fuchs/Endothelial", donorAge: 60,
            baselineEcd: 2700, baselineCv: 36, baselineHex: 56,
            visit3m: { ecd: 2300, cv: 38, hex: 54 }, visit6m: { ecd: 1700, cv: 42, hex: 50 },
            visit12m: { ecd: 1000, cv: 46, hex: 45 }, rejectionBy12m: false,
        })
        const ecd = within(screen.getByRole("region", { name: "Predicted ECD" }))
        expect(ecd.getByText("542")).toBeInTheDocument()
        expect(ecd.getByText("485–641")).toBeInTheDocument()
        const risk = within(screen.getByRole("region", { name: "Risk after this visit" }))
        expect(risk.getByText("84%")).toBeInTheDocument()
        expect(screen.getByText(/early cell loss \(hazard ×22.52\)/)).toBeInTheDocument()
        expect(screen.getByText(/\[descriptive\]/)).toBeInTheDocument()
        expect(screen.getByText(/Models developed on: simulated data \(method development\)/)).toBeInTheDocument()
    })

    it("accepts a missed 3-month visit", async () => {
        vi.mocked(recommendFollowup).mockResolvedValue(RED)
        renderApp("/post-transplant", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndSubmit({ skip3m: true })

        await screen.findByText("Red alert")
        expect(vi.mocked(recommendFollowup).mock.calls[0][0].visit3m).toBeNull()
    })

    it("lists missing values instead of calling the server", async () => {
        renderApp("/post-transplant", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndSubmit({ leaveOut: "12-month ECD" })

        expect(await screen.findByText(/Missing or not a number: 12-month ECD/)).toBeInTheDocument()
        expect(recommendFollowup).not.toHaveBeenCalled()
    })

    it("shows a server rejection", async () => {
        vi.mocked(recommendFollowup).mockRejectedValue(
            new ApiError(503, "The follow-up model is unavailable. Try again later.", {}, "MODEL_NOT_READY"))
        renderApp("/post-transplant", makeAuth({ user: makeUser("DOCTOR") }))

        await fillAndSubmit()

        expect(await screen.findByText("The follow-up model is unavailable. Try again later.")).toBeInTheDocument()
    })
})
