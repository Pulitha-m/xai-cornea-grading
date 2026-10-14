import { screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"
import type { ManagedUser } from "@/types/auth"

function account(id: number, overrides: Partial<ManagedUser>): ManagedUser {
    return {
        id,
        username: `user${id}`,
        email: `user${id}@nebsl.test`,
        fullName: `User ${id}`,
        role: "NURSE",
        enabled: true,
        lastLoginAt: null,
        createdAt: "2026-01-01T00:00:00Z",
        ...overrides,
    }
}

vi.mock("@/api/users", () => ({
    USERS_QUERY_KEY: ["users"],
    listUsers: vi.fn().mockImplementation(async () => [
        account(2, { lastLoginAt: new Date().toISOString() }),
        account(3, { lastLoginAt: "2020-01-01T00:00:00Z" }),
        account(4, { enabled: false }),
    ]),
    createUser: vi.fn(),
    assignRole: vi.fn(),
    setUserEnabled: vi.fn(),
}))

function statValue(label: string) {
    const term = screen.getByText(label, { selector: "dt" })
    return within(term.parentElement!).getAllByRole("definition")[0]
}

describe("AdminDashboard", () => {
    it("summarises staff accounts from the user directory", async () => {
        renderApp("/admin/dashboard", makeAuth({ user: makeUser("ADMIN") }))

        expect(await screen.findByText("User 2")).toBeInTheDocument()
        expect(statValue("Staff accounts")).toHaveTextContent("3")
        expect(statValue("Active")).toHaveTextContent("2")
        expect(statValue("Disabled")).toHaveTextContent("1")
        expect(statValue("Signed in this week")).toHaveTextContent("1")
    })
})
