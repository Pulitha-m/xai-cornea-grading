import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { applyCaseImport, checkCaseImport, listCandidates, recentCases, type ImportReport } from "@/api/cases"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/cases"), async (importOriginal) => ({
    ...(await importOriginal()),
    recentCases: vi.fn(),
    listCandidates: vi.fn(),
    checkCaseImport: vi.fn(),
    applyCaseImport: vi.fn(),
}))

function report(overrides: Partial<ImportReport>): ImportReport {
    return {
        applied: false, mode: "create", rows: 2, created: 2, updated: 0, skipped: 0, withErrors: 0, ignoredColumns: [],
        details: [
            { row: 2, tissueId: "12656R", action: "create", errors: [] },
            { row: 3, tissueId: "12657L", action: "create", errors: [] },
        ],
        ...overrides,
    }
}

function csv() {
    return new File(["tissue_id,ECD\n12656R,2400\n12657L,2500\n"], "cases.csv", { type: "text/csv" })
}

beforeEach(() => {
    vi.mocked(recentCases).mockResolvedValue([])
    vi.mocked(listCandidates).mockResolvedValue([])
})

describe("Import cases", () => {
    it("checks the file and offers no import while a row has errors", async () => {
        vi.mocked(checkCaseImport).mockResolvedValue(report({
            created: 1, withErrors: 1, ignoredColumns: ["Comments"],
            details: [
                { row: 2, tissueId: "12656R", action: "create", errors: [] },
                { row: 3, tissueId: "CASE-1", action: "error", errors: ["Enter the tissue ID as five digits followed by R or L, for example 12656R."] },
            ],
        }))
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        const card = (await screen.findByRole("heading", { name: "Import cases" })).closest("section")!
        await user.upload(within(card).getByLabelText("File"), csv())

        expect(await within(card).findByText(/1 with errors/)).toBeInTheDocument()
        expect(within(card).getByText("Error")).toBeInTheDocument()
        expect(within(card).getByText(/five digits followed by R or L/)).toBeInTheDocument()
        expect(within(card).getByText("Ignored columns: Comments")).toBeInTheDocument()
        expect(within(card).queryByRole("button", { name: /^Import/ })).not.toBeInTheDocument()
        expect(applyCaseImport).not.toHaveBeenCalled()
    })

    it("imports a valid file after the check and shows what was done", async () => {
        vi.mocked(checkCaseImport).mockResolvedValue(report({}))
        vi.mocked(applyCaseImport).mockResolvedValue(report({ applied: true }))
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("DOCTOR") }))

        const card = (await screen.findByRole("heading", { name: "Import cases" })).closest("section")!
        await user.upload(within(card).getByLabelText("File"), csv())
        await user.click(await within(card).findByRole("button", { name: "Import 2 cases" }))

        expect(await within(card).findByText(/Imported: 2 new, 0 updated, 0 skipped/)).toBeInTheDocument()
        expect(vi.mocked(applyCaseImport).mock.calls[0][1]).toBe("create")
        expect(within(card).queryByRole("button", { name: /^Import/ })).not.toBeInTheDocument()
    })

    it("warns that a timed-out import may still be running and does not offer to import again", async () => {
        vi.mocked(checkCaseImport).mockResolvedValue(report({}))
        vi.mocked(applyCaseImport).mockRejectedValue(new ApiError(504, "Something went wrong. Please try again."))
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        const card = (await screen.findByRole("heading", { name: "Import cases" })).closest("section")!
        await user.upload(within(card).getByLabelText("File"), csv())
        await user.click(await within(card).findByRole("button", { name: "Import 2 cases" }))

        expect(await within(card).findByText(/may still be running or may already have finished/)).toBeInTheDocument()
        expect(within(card).queryByText(/Something went wrong/)).not.toBeInTheDocument()
        expect(within(card).queryByRole("button", { name: /^Import/ })).not.toBeInTheDocument()
    })

    it("checks again in update mode", async () => {
        vi.mocked(checkCaseImport).mockResolvedValue(report({}))
        const user = userEvent.setup()
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        const card = (await screen.findByRole("heading", { name: "Import cases" })).closest("section")!
        await user.upload(within(card).getByLabelText("File"), csv())
        await within(card).findByRole("button", { name: "Import 2 cases" })
        await user.click(within(card).getByLabelText(/Update their details/))

        expect(vi.mocked(checkCaseImport).mock.calls.at(-1)?.[1]).toBe("update")
    })
})
