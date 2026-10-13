import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import { makeAuth, makeUser, renderApp, renderAppWithLogin } from "@/test/auth-test-utils"

vi.mock("@/api/users", () => ({
    USERS_QUERY_KEY: ["users"],
    listUsers: vi.fn().mockResolvedValue([]),
    createUser: vi.fn(),
    assignRole: vi.fn(),
    setUserEnabled: vi.fn(),
}))

async function fillAndSubmit(identifier: string, password: string) {
    const user = userEvent.setup()
    if (identifier) await user.type(screen.getByLabelText("Email or username"), identifier)
    if (password) await user.type(screen.getByLabelText("Password"), password)
    await user.click(screen.getByRole("button", { name: "Sign in" }))
    return user
}

describe("LoginPage", () => {
    it("shows inline validation and does not call the API for empty fields", async () => {
        const auth = makeAuth()
        renderApp("/login", auth)

        await fillAndSubmit("", "")

        expect(screen.getByText("Enter your email or username.")).toBeInTheDocument()
        expect(screen.getByText("Enter your password.")).toBeInTheDocument()
        expect(screen.getByLabelText("Email or username")).toHaveAttribute("aria-invalid", "true")
        expect(screen.getByLabelText("Email or username")).toHaveFocus()
        expect(auth.login).not.toHaveBeenCalled()
    })

    it("shows the generic error for invalid credentials and clears the password", async () => {
        const auth = makeAuth({
            login: vi.fn().mockRejectedValue(new ApiError(401, "Invalid username/email or password.")),
        })
        renderApp("/login", auth)

        await fillAndSubmit("dr.silva", "wrong-password")

        expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username/email or password.")
        expect(screen.getByLabelText("Password")).toHaveValue("")
        expect(auth.login).toHaveBeenCalledWith({ identifier: "dr.silva", password: "wrong-password", rememberMe: false })
    })

    it("never shows raw errors from unexpected failures", async () => {
        const auth = makeAuth({
            login: vi.fn().mockRejectedValue(new TypeError("NullPointerException at com.cornealai...")),
        })
        renderApp("/login", auth)

        await fillAndSubmit("dr.silva", "pw")

        const alert = await screen.findByRole("alert")
        expect(alert).toHaveTextContent("Unable to sign in. Please try again.")
        expect(alert).not.toHaveTextContent("NullPointerException")
    })

    it("redirects to the role dashboard after signing in", async () => {
        const { router } = renderAppWithLogin("/login", makeUser("DOCTOR"))

        await fillAndSubmit("dr.silva", "Correct-Horse-9")

        expect(await screen.findByRole("heading", { name: "Clinical review" })).toBeInTheDocument()
        expect(router.state.location.pathname).toBe("/doctor/dashboard")
    })

    it("returns to the originally requested page after signing in", async () => {
        const { router } = renderAppWithLogin(
            { pathname: "/login", state: { from: { pathname: "/nurse/dashboard", search: "?case=3", hash: "" } } },
            makeUser("NURSE"),
        )

        await fillAndSubmit("nurse", "Correct-Horse-9")

        expect(await screen.findByRole("heading", { name: "Clinical workflow" })).toBeInTheDocument()
        expect(router.state.location.pathname).toBe("/nurse/dashboard")
        expect(router.state.location.search).toBe("?case=3")
    })

    it("sends remember-me when selected", async () => {
        const auth = makeAuth({ login: vi.fn().mockResolvedValue(makeUser("DOCTOR")) })
        renderApp("/login", auth)
        const user = userEvent.setup()

        await user.type(screen.getByLabelText("Email or username"), "dr.silva")
        await user.type(screen.getByLabelText("Password"), "Correct-Horse-9")
        await user.click(screen.getByLabelText("Keep me signed in on this device"))
        await user.click(screen.getByRole("button", { name: "Sign in" }))

        expect(auth.login).toHaveBeenCalledWith(expect.objectContaining({ rememberMe: true }))
    })

    it("toggles password visibility", async () => {
        renderApp("/login", makeAuth())
        const user = userEvent.setup()
        const password = screen.getByLabelText("Password")

        expect(password).toHaveAttribute("type", "password")
        await user.click(screen.getByRole("button", { name: "Show password" }))
        expect(password).toHaveAttribute("type", "text")
        await user.click(screen.getByRole("button", { name: "Hide password" }))
        expect(password).toHaveAttribute("type", "password")
    })

    it("tells the user when their session expired", () => {
        renderApp("/login", makeAuth({ sessionExpired: true }))

        expect(screen.getByText("Your session has expired. Please sign in again.")).toBeInTheDocument()
    })

    it("redirects an already signed-in user away from the login page", async () => {
        const { router } = renderApp("/login", makeAuth({ user: makeUser("ADMIN") }))

        await vi.waitFor(() => expect(router.state.location.pathname).toBe("/admin/dashboard"))
    })
})
