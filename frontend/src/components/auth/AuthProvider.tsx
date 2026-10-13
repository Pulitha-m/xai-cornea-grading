import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import * as authApi from "@/api/auth"
import { registerSessionHandlers, setAccessToken } from "@/lib/api-client"
import { AuthContext, type AuthContextValue, type AuthStatus } from "@/lib/auth-context"
import type { AuthResponse, LoginRequest, Permission, Role, User } from "@/types/auth"

/** Renew the access token this long before it expires. */
const REFRESH_LEAD_MS = 60_000
const MIN_REFRESH_DELAY_MS = 5_000
const CHANNEL_NAME = "cornealai-auth"

/**
 * Owns the authentication state. The access token is kept in memory only; on
 * page load the session is restored from the HttpOnly refresh cookie.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
    const queryClient = useQueryClient()
    const [status, setStatus] = useState<AuthStatus>("loading")
    const [user, setUser] = useState<User | null>(null)
    const [sessionExpired, setSessionExpired] = useState(false)

    const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
    const channel = useRef<BroadcastChannel | null>(null)

    const clearRefreshTimer = () => {
        if (refreshTimer.current) {
            clearTimeout(refreshTimer.current)
            refreshTimer.current = null
        }
    }

    const endSession = useCallback(
        (expired: boolean) => {
            clearRefreshTimer()
            setAccessToken(null)
            setUser(null)
            setStatus("unauthenticated")
            setSessionExpired(expired)
            queryClient.clear()
        },
        [queryClient],
    )

    // Indirection so the scheduled refresh can call back into startSession.
    const scheduledRefresh = useRef<() => void>(() => {})

    const startSession = useCallback((response: AuthResponse) => {
        setAccessToken(response.accessToken)
        setUser(response.user)
        setStatus("authenticated")
        setSessionExpired(false)

        clearRefreshTimer()
        const delay = Math.max(response.expiresIn * 1000 - REFRESH_LEAD_MS, MIN_REFRESH_DELAY_MS)
        refreshTimer.current = setTimeout(() => scheduledRefresh.current(), delay)
    }, [])

    useEffect(() => {
        scheduledRefresh.current = () => {
            authApi.refreshSession().then(startSession, () => endSession(true))
        }
    }, [startSession, endSession])

    const tryRefresh = useCallback(async () => {
        try {
            startSession(await authApi.refreshSession())
            return true
        } catch {
            return false
        }
    }, [startSession])

    // Restore the session on first load and wire the API client's 401 recovery.
    useEffect(() => {
        registerSessionHandlers({
            refresh: tryRefresh,
            onSessionExpired: () => endSession(true),
        })

        authApi.refreshSession().then(startSession, () => endSession(false))

        return () => {
            registerSessionHandlers(null)
            clearRefreshTimer()
        }
    }, [tryRefresh, startSession, endSession])

    // Sign out other tabs when this one logs out.
    useEffect(() => {
        if (typeof BroadcastChannel === "undefined") {
            return
        }
        const bc = new BroadcastChannel(CHANNEL_NAME)
        bc.onmessage = (event) => {
            if (event.data === "logout") {
                endSession(false)
            }
        }
        channel.current = bc
        return () => {
            bc.close()
            channel.current = null
        }
    }, [endSession])

    const login = useCallback(
        async (request: LoginRequest) => {
            const response = await authApi.login(request)
            startSession(response)
            return response.user
        },
        [startSession],
    )

    const logout = useCallback(async () => {
        try {
            await authApi.logout()
        } catch {
            // Clear local state even if the server could not be reached.
        } finally {
            endSession(false)
            channel.current?.postMessage("logout")
        }
    }, [endSession])

    const value = useMemo<AuthContextValue>(
        () => ({
            status,
            user,
            sessionExpired,
            login,
            logout,
            hasRole: (...roles: Role[]) => user !== null && roles.includes(user.role),
            hasPermission: (permission: Permission) => user?.permissions.includes(permission) ?? false,
        }),
        [status, user, sessionExpired, login, logout],
    )

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
