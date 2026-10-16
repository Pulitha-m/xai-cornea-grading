import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import AnalysisPage from "./analysis-page"
import { parseEcd } from "@/lib/ecd"
// Responses captured from ml-service; the backend passes them through unchanged
// and checks the same file in MlServiceContractTest.
import responses from "../../../backend/src/test/resources/contracts/ml_service_analyze_responses.json"

function mockFetch(body: unknown) {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    return fetchMock
}

function renderPage() {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(
        <QueryClientProvider client={client}>
            <AnalysisPage />
        </QueryClientProvider>,
    )
    return userEvent.setup()
}

async function fillForm(user: ReturnType<typeof userEvent.setup>, ecd: string) {
    await user.type(screen.getByLabelText("Case ID"), "case-1")
    await user.type(screen.getByLabelText("Specular microscopy image URL"), "http://example/img.jpg")
    if (ecd) await user.type(screen.getByLabelText("ECD (cells/mm²)"), ecd)
    await user.click(screen.getByRole("button", { name: "Grade tissue" }))
}

function sentBody(fetchMock: ReturnType<typeof vi.fn>) {
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    return JSON.parse(init.body as string)
}

afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
})

describe("parseEcd", () => {
    it("treats blank as unavailable", () => {
        expect(parseEcd("  ")).toEqual({ ecd: null, error: null })
    })

    it("accepts the API range boundaries", () => {
        expect(parseEcd("6000").ecd).toBe(6000)
        expect(parseEcd("0").error).not.toBeNull()
        expect(parseEcd("6000.5").error).not.toBeNull()
        expect(parseEcd("abc").error).not.toBeNull()
    })
})

describe("AnalysisPage", () => {
    it("sends ECD and shows the ECD-based grade with its band and caveats", async () => {
        const fetchMock = mockFetch(responses.completed)
        const user = renderPage()

        await fillForm(user, "2400")

        expect(await screen.findByTestId("grade")).toHaveProperty("textContent", "A")
        expect(sentBody(fetchMock)).toEqual({ caseId: "case-1", imageUrl: "http://example/img.jpg", ecd: 2400 })
        expect(screen.getByText("2232 < ECD ≤ 2497")).toBeTruthy()
        expect(screen.getByText(/not model confidence/)).toBeTruthy()
        expect(screen.getByText("A: 89%")).toBeTruthy()
        expect(screen.getByText(/Specialist confirmation required/)).toBeTruthy()
        expect(screen.getByText(/Cellular analysis: not implemented yet/)).toBeTruthy()
    })

    it("sends null ECD when blank and shows that manual grading is required", async () => {
        const fetchMock = mockFetch(responses.review_required)
        const user = renderPage()

        await fillForm(user, "")

        expect(await screen.findByText(/manual grading required/)).toBeTruthy()
        expect(sentBody(fetchMock).ecd).toBeNull()
        expect(screen.queryByTestId("grade")).toBeNull()
    })

    it("rejects an out-of-range ECD without calling the API", async () => {
        const fetchMock = mockFetch(responses.completed)
        const user = renderPage()

        await fillForm(user, "7000")

        expect(screen.getByRole("alert").textContent).toMatch(/at most 6000/)
        expect(fetchMock).not.toHaveBeenCalled()
    })
})
