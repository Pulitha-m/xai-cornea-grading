import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { listAuditEvents } from "@/api/audit"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

vi.mock(import("@/api/audit"), async (importOriginal) => ({
    ...(await importOriginal()),
    listAuditEvents: vi.fn(),
}))

describe("Audit log", () => {
    it("shows administrators who decrypted what", async () => {
        vi.mocked(listAuditEvents).mockResolvedValue([{
            id: "e1", occurredAt: "2026-10-20T09:00:00Z", userId: 2, username: "dr.silva", action: "SEROLOGY_VIEW",
            subjectType: "case", subjectId: "0827a01e-c576-4b04-819d-c681fbb1c7c1", detail: null,
        }])
        renderApp("/audit", makeAuth({ user: makeUser("ADMIN") }))

        expect(await screen.findByText("Viewed serology")).toBeInTheDocument()
        expect(screen.getByText("dr.silva")).toBeInTheDocument()
        expect(screen.getByText("case 0827a01e")).toBeInTheDocument()
    })

    it("is not available to clinicians", async () => {
        renderApp("/audit", makeAuth({ user: makeUser("DOCTOR") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
        expect(listAuditEvents).not.toHaveBeenCalled()
    })
})
