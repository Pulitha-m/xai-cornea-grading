/**
 * HTTP client for the Corneal-AI API.
 *
 * - The access token lives only in memory (never localStorage) and is sent as a Bearer header.
 * - The refresh token is an HttpOnly cookie the browser manages; JS never sees it.
 * - Cookie-authenticated auth endpoints send the XSRF-TOKEN cookie back as X-XSRF-TOKEN.
 * - A 401 on a protected call triggers one silent refresh + retry before the session is ended.
 */

// Empty by default: the API is reached through the same-origin /api proxy (nginx / Vite).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ""

const XSRF_COOKIE = "XSRF-TOKEN"
const XSRF_HEADER = "X-XSRF-TOKEN"

const GENERIC_ERROR = "Something went wrong. Please try again."
const NETWORK_ERROR = "Unable to reach the server. Check your connection and try again."

export class ApiError extends Error {
    readonly status: number
    readonly fieldErrors: Record<string, string>

    constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
        super(message)
        this.name = "ApiError"
        this.status = status
        this.fieldErrors = fieldErrors
    }
}

let accessToken: string | null = null

export function setAccessToken(token: string | null) {
    accessToken = token
}

export function getAccessToken() {
    return accessToken
}

interface SessionHandlers {
    /** Attempts a silent refresh; resolves true if a new access token was stored. */
    refresh: () => Promise<boolean>
    /** Called when the session cannot be recovered. */
    onSessionExpired: () => void
}

let sessionHandlers: SessionHandlers | null = null

export function registerSessionHandlers(handlers: SessionHandlers | null) {
    sessionHandlers = handlers
}

interface RequestOptions {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
    body?: unknown
    /** Attach the Bearer token and recover from 401 via refresh (default true). */
    auth?: boolean
    /** Send the CSRF header (cookie-authenticated auth endpoints). */
    csrf?: boolean
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { auth = true } = options
    const response = await send(path, options)

    if (response.status === 401 && auth && sessionHandlers) {
        const refreshed = await sessionHandlers.refresh()
        if (refreshed) {
            return parse<T>(await send(path, options))
        }
        sessionHandlers.onSessionExpired()
    }

    return parse<T>(response)
}

async function send(path: string, { method = "GET", body, auth = true, csrf = false }: RequestOptions) {
    const headers: Record<string, string> = { Accept: "application/json" }

    if (body !== undefined) {
        headers["Content-Type"] = "application/json"
    }
    if (auth && accessToken) {
        headers.Authorization = `Bearer ${accessToken}`
    }
    if (csrf) {
        headers[XSRF_HEADER] = await ensureCsrfToken()
    }

    try {
        return await fetch(`${API_BASE_URL}${path}`, {
            method,
            headers,
            body: body === undefined ? undefined : JSON.stringify(body),
            credentials: "include",
        })
    } catch {
        throw new ApiError(0, NETWORK_ERROR)
    }
}

async function parse<T>(response: Response): Promise<T> {
    if (response.ok) {
        if (response.status === 204) {
            return undefined as T
        }
        return (await response.json()) as T
    }

    throw await toApiError(response)
}

/** Converts an error response into a message that is safe to show to the user. */
async function toApiError(response: Response): Promise<ApiError> {
    if (response.status >= 500) {
        return new ApiError(response.status, GENERIC_ERROR)
    }

    let payload: { message?: unknown; fieldErrors?: unknown } = {}
    try {
        payload = await response.json()
    } catch {
        // Non-JSON body (e.g. proxy error page): fall through to the generic message.
    }

    const message = typeof payload.message === "string" && payload.message ? payload.message : GENERIC_ERROR
    const fieldErrors =
        payload.fieldErrors && typeof payload.fieldErrors === "object"
            ? (payload.fieldErrors as Record<string, string>)
            : {}

    return new ApiError(response.status, message, fieldErrors)
}

function readCookie(name: string): string | null {
    const match = document.cookie
        .split("; ")
        .find((cookie) => cookie.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

async function ensureCsrfToken(): Promise<string> {
    const existing = readCookie(XSRF_COOKIE)
    if (existing) {
        return existing
    }

    try {
        await fetch(`${API_BASE_URL}/api/auth/csrf`, { credentials: "include" })
    } catch {
        throw new ApiError(0, NETWORK_ERROR)
    }

    const token = readCookie(XSRF_COOKIE)
    if (!token) {
        throw new ApiError(0, "Unable to establish a secure session. Please reload the page.")
    }
    return token
}
