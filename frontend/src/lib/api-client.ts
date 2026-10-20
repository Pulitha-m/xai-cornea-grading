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
    /** Stable machine-readable reason from the server (e.g. INVALID_IMAGE_DOMAIN), when provided. */
    readonly code: string | null

    constructor(status: number, message: string, fieldErrors: Record<string, string> = {}, code: string | null = null) {
        super(message)
        this.name = "ApiError"
        this.status = status
        this.fieldErrors = fieldErrors
        this.code = code
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
    let text = ""
    try {
        text = await response.text()
    } catch {
        // Unreadable body: fall through to the generic message.
    }
    return errorFromBody(response.status, text)
}

/**
 * Server error bodies are built to be safe for display. A 5xx is only shown verbatim
 * when it carries a server-assigned code; otherwise (e.g. a proxy error page) a
 * generic message is used.
 */
function errorFromBody(status: number, text: string): ApiError {
    let payload: { message?: unknown; fieldErrors?: unknown; code?: unknown } = {}
    try {
        payload = JSON.parse(text)
    } catch {
        // Non-JSON body: fall through to the generic message.
    }

    const code = typeof payload.code === "string" && payload.code ? payload.code : null
    if (status >= 500 && code === null) {
        return new ApiError(status, GENERIC_ERROR)
    }

    const message = typeof payload.message === "string" && payload.message ? payload.message : GENERIC_ERROR
    const fieldErrors =
        payload.fieldErrors && typeof payload.fieldErrors === "object"
            ? (payload.fieldErrors as Record<string, string>)
            : {}

    return new ApiError(status, message, fieldErrors, code)
}

interface UploadOptions {
    /** Called with the fraction of the request body sent, from 0 to 1. */
    onProgress?: (fraction: number) => void
}

/**
 * Multipart upload with progress (fetch cannot report upload progress). Uses the same
 * Bearer token, 401 refresh-and-retry and error handling as {@link apiRequest}.
 */
export async function apiUpload<T>(path: string, form: FormData, options: UploadOptions = {}): Promise<T> {
    let result = await sendUpload(path, form, options)

    if (result.status === 401 && sessionHandlers) {
        const refreshed = await sessionHandlers.refresh()
        if (refreshed) {
            result = await sendUpload(path, form, options)
        } else {
            sessionHandlers.onSessionExpired()
        }
    }

    if (result.status >= 200 && result.status < 300) {
        return JSON.parse(result.text) as T
    }
    throw errorFromBody(result.status, result.text)
}

function sendUpload(path: string, form: FormData, { onProgress }: UploadOptions): Promise<{ status: number; text: string }> {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open("POST", `${API_BASE_URL}${path}`)
        xhr.withCredentials = true
        xhr.setRequestHeader("Accept", "application/json")
        if (accessToken) {
            xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`)
        }
        if (onProgress) {
            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    onProgress(event.loaded / event.total)
                }
            }
        }
        xhr.onload = () => resolve({ status: xhr.status, text: xhr.responseText })
        xhr.onerror = () => reject(new ApiError(0, NETWORK_ERROR))
        xhr.ontimeout = () => reject(new ApiError(0, "The upload timed out. Try again."))
        xhr.send(form)
    })
}

/**
 * Binary download (e.g. a decrypted case image for display) with the same Bearer token and
 * 401 refresh-and-retry as {@link apiRequest}. The caller owns any object URL made from it.
 */
export async function apiBlob(path: string, accept = "image/*"): Promise<Blob> {
    const fetchBlob = async () => {
        const headers: Record<string, string> = { Accept: accept }
        if (accessToken) headers.Authorization = `Bearer ${accessToken}`
        try {
            return await fetch(`${API_BASE_URL}${path}`, { headers, credentials: "include" })
        } catch {
            throw new ApiError(0, NETWORK_ERROR)
        }
    }

    let response = await fetchBlob()
    if (response.status === 401 && sessionHandlers) {
        if (await sessionHandlers.refresh()) {
            response = await fetchBlob()
        } else {
            sessionHandlers.onSessionExpired()
        }
    }
    if (!response.ok) {
        throw await toApiError(response)
    }
    return response.blob()
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
