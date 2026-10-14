import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { makeAuth, makeUser, renderApp } from "@/test/auth-test-utils"

// Dashboards fetch data; keep these tests about routing only.
vi.mock("@/api/users", () => ({
    USERS_QUERY_KEY: ["users"],
    listUsers: vi.fn().mockResolvedValue([]),
    createUser: vi.fn(),
    assignRole: vi.fn(),
    setUserEnabled: vi.fn(),
}))

describe("ProtectedRoute", () => {
    it("redirects unauthenticated users to login and preserves the destination", async () => {
        const { router } = renderApp("/doctor/dashboard?case=7", makeAuth())

        expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument()
        expect(router.state.location.pathname).toBe("/login")
        expect(router.state.location.state.from).toMatchObject({ pathname: "/doctor/dashboard", search: "?case=7" })
    })

    it("renders nothing protected while the session is being restored", () => {
        renderApp("/doctor/dashboard", makeAuth({ status: "loading" }))

        expect(screen.getByRole("status")).toHaveTextContent("Checking your session")
        expect(screen.queryByText("Clinical review")).not.toBeInTheDocument()
    })

    it("sends a signed-in user from / to their role's dashboard", async () => {
        const { router } = renderApp("/", makeAuth({ user: makeUser("MANAGER") }))

        expect(await screen.findByRole("heading", { name: "Operations" })).toBeInTheDocument()
        expect(router.state.location.pathname).toBe("/manager/dashboard")
    })
})

describe("RoleGuard", () => {
    it("shows the access-denied page instead of admin content for a nurse", async () => {
        renderApp("/admin/dashboard", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
        expect(screen.queryByText("Administration")).not.toBeInTheDocument()
        expect(screen.queryByText("Create account")).not.toBeInTheDocument()
    })

    it("does not render clinical tools for support staff on a doctor route", async () => {
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("SUPPORT_STAFF") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
        expect(screen.queryByText("Run corneal analysis")).not.toBeInTheDocument()
    })

    it("renders the dashboard for the permitted role", async () => {
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("DOCTOR") }))

        expect(await screen.findByRole("heading", { name: "Clinical review" })).toBeInTheDocument()
        expect(screen.getByText("Run corneal analysis")).toBeInTheDocument()
    })
})

describe("Navigation", () => {
    it("only lists navigation items the user may access", async () => {
        renderApp("/nurse/dashboard", makeAuth({ user: makeUser("NURSE") }))

        const nav = await screen.findByRole("navigation", { name: "Main" })
        expect(nav).toHaveTextContent("Nurse dashboard")
        expect(nav).not.toHaveTextContent("Admin dashboard")
        expect(nav).not.toHaveTextContent("Doctor dashboard")
        expect(nav).toHaveTextContent("Donor cases")
        expect(nav).not.toHaveTextContent("Audit log")
    })
})

describe("Planned modules", () => {
    it("shows a coming-soon screen to a permitted role", async () => {
        renderApp("/cases", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByRole("heading", { name: "Donor cases" })).toBeInTheDocument()
        expect(screen.getByText("This module is not available yet")).toBeInTheDocument()
    })

    it("applies the same role guard as real pages", async () => {
        renderApp("/audit", makeAuth({ user: makeUser("NURSE") }))

        expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument()
    })
})

describe("AppLayout", () => {
    it("signs the user out from the sidebar", async () => {
        const auth = makeAuth({ user: makeUser("DOCTOR") })
        renderApp("/doctor/dashboard", auth)

        await userEvent.setup().click(await screen.findByRole("button", { name: "Sign out" }))

        expect(auth.logout).toHaveBeenCalledTimes(1)
    })

    it("opens and closes the navigation drawer", async () => {
        const user = userEvent.setup()
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("DOCTOR") }))

        const menuButton = await screen.findByRole("button", { name: "Open navigation" })
        await user.click(menuButton)
        expect(screen.getByRole("dialog", { name: "Navigation" })).toBeInTheDocument()

        await user.keyboard("{Escape}")
        expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument()
        expect(menuButton).toHaveFocus()
    })

    it("keeps keyboard focus inside the open drawer", async () => {
        const user = userEvent.setup()
        renderApp("/doctor/dashboard", makeAuth({ user: makeUser("DOCTOR") }))

        await user.click(await screen.findByRole("button", { name: "Open navigation" }))
        const drawer = screen.getByRole("dialog", { name: "Navigation" })
        const closeButton = within(drawer).getByRole("button", { name: "Close navigation" })
        const signOut = within(drawer).getByRole("button", { name: "Sign out" })
        expect(closeButton).toHaveFocus()

        await user.tab({ shift: true })
        expect(signOut).toHaveFocus()

        await user.tab()
        expect(closeButton).toHaveFocus()
    })
})

describe("NotFoundPage", () => {
    it("renders for unknown routes", async () => {
        renderApp("/does-not-exist", makeAuth())

        expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument()
    })
})
