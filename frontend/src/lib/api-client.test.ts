import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiRequest, registerSessionHandlers, setAccessToken } from "@/lib/api-client"

function jsonResponse(status: number, body: unknown) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("apiRequest", () => {
    const fetchMock = vi.fn<typeof fetch>()

    beforeEach(() => {
        vi.stubGlobal("fetch", fetchMock)
        setAccessToken("token-1")
    })

    afterEach(() => {
        fetchMock.mockReset()
        vi.unstubAllGlobals()
        registerSessionHandlers(null)
        setAccessToken(null)
        document.cookie = "XSRF-TOKEN=; expires=Thu, 01 Jan 1970 00:00:00 GMT"
    })

    it("sends the in-memory access token as a Bearer header", async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }))

        await apiRequest("/api/auth/me")

        const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
        expect(headers.Authorization).toBe("Bearer token-1")
    })

    it("refreshes once on 401 and retries with the new token", async () => {
        const refresh = vi.fn(async () => {
            setAccessToken("token-2")
            return true
        })
        registerSessionHandlers({ refresh, onSessionExpired: vi.fn() })
        fetchMock
            .mockResolvedValueOnce(jsonResponse(401, { message: "expired" }))
            .mockResolvedValueOnce(jsonResponse(200, { id: 1 }))

        await expect(apiRequest("/api/auth/me")).resolves.toEqual({ id: 1 })

        expect(refresh).toHaveBeenCalledTimes(1)
        const retryHeaders = fetchMock.mock.calls[1][1]?.headers as Record<string, string>
        expect(retryHeaders.Authorization).toBe("Bearer token-2")
    })

    it("ends the session when the refresh fails", async () => {
        const onSessionExpired = vi.fn()
        registerSessionHandlers({ refresh: vi.fn().mockResolvedValue(false), onSessionExpired })
        fetchMock.mockResolvedValue(jsonResponse(401, { message: "Your session has expired. Please sign in again." }))

        await expect(apiRequest("/api/users")).rejects.toMatchObject({ status: 401 })
        expect(onSessionExpired).toHaveBeenCalledTimes(1)
    })

    it("surfaces 403 without attempting a refresh", async () => {
        const refresh = vi.fn()
        registerSessionHandlers({ refresh, onSessionExpired: vi.fn() })
        fetchMock.mockResolvedValue(jsonResponse(403, { message: "You do not have permission to perform this action." }))

        await expect(apiRequest("/api/users")).rejects.toMatchObject({
            status: 403,
            message: "You do not have permission to perform this action.",
        })
        expect(refresh).not.toHaveBeenCalled()
    })

    it("hides server error details behind a generic message", async () => {
        fetchMock.mockResolvedValue(jsonResponse(500, { message: "org.hibernate.exception.SQLGrammarException ..." }))

        const error = await apiRequest("/api/users").catch((e: unknown) => e)
        expect(error).toBeInstanceOf(ApiError)
        expect((error as ApiError).message).toBe("Something went wrong. Please try again.")
    })

    it("reports network failures with a friendly message", async () => {
        fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))

        await expect(apiRequest("/api/users")).rejects.toMatchObject({
            status: 0,
            message: "Unable to reach the server. Check your connection and try again.",
        })
    })

    it("fetches and echoes the XSRF cookie for cookie-authenticated calls", async () => {
        fetchMock
            .mockImplementationOnce(async () => {
                document.cookie = "XSRF-TOKEN=abc123; path=/"
                return new Response(null, { status: 204 })
            })
            .mockResolvedValueOnce(new Response(null, { status: 204 }))

        await apiRequest("/api/auth/logout", { method: "POST", auth: false, csrf: true })

        expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/csrf")
        const headers = fetchMock.mock.calls[1][1]?.headers as Record<string, string>
        expect(headers["X-XSRF-TOKEN"]).toBe("abc123")
        expect(headers.Authorization).toBeUndefined()
    })
})
