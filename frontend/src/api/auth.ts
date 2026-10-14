import { ApiError, apiRequest } from "@/lib/api-client"
import type { AuthResponse, LoginRequest, User } from "@/types/auth"

export function login(request: LoginRequest): Promise<AuthResponse> {
    return apiRequest<AuthResponse>("/api/auth/login", {
        method: "POST",
        body: request,
        auth: false,
        csrf: true,
    })
}

export function logout(): Promise<void> {
    return apiRequest<void>("/api/auth/logout", { method: "POST", auth: false, csrf: true })
}

export function fetchCurrentUser(): Promise<User> {
    return apiRequest<User>("/api/auth/me")
}

let inflightRefresh: Promise<AuthResponse> | null = null

/**
 * Exchanges the HttpOnly refresh cookie for a new access token.
 * Concurrent callers share one request, so the token is rotated only once.
 */
export function refreshSession(): Promise<AuthResponse> {
    inflightRefresh ??= requestRefresh().finally(() => {
        inflightRefresh = null
    })
    return inflightRefresh
}

const RETRY_DELAY_MS = 400

async function requestRefresh(): Promise<AuthResponse> {
    const send = () => apiRequest<AuthResponse>("/api/auth/refresh", { method: "POST", auth: false, csrf: true })

    try {
        return await send()
    } catch (error) {
        // Another tab may have just rotated the shared cookie; retry once with the new one.
        if (error instanceof ApiError && error.status === 401) {
            await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS))
            return send()
        }
        throw error
    }
}
