import { useState } from "react"
import { render } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryRouter, RouterProvider, type InitialEntry } from "react-router-dom"
import { vi } from "vitest"
import { AuthContext, type AuthContextValue } from "@/lib/auth-context"
import { routes } from "@/routes"
import type { Role, User } from "@/types/auth"

const PERMISSIONS: Record<Role, User["permissions"]> = {
    ADMIN: ["roles:assign", "users:manage", "users:read"],
    MANAGER: ["users:read"],
    DOCTOR: ["analysis:run"],
    NURSE: ["analysis:run"],
    SUPPORT_STAFF: [],
}

export function makeUser(role: Role): User {
    return {
        id: 1,
        username: `${role.toLowerCase()}.user`,
        email: `${role.toLowerCase()}@cornealai.test`,
        fullName: `Test ${role}`,
        role,
        permissions: PERMISSIONS[role],
    }
}

export function makeAuth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
    const user = overrides.user ?? null
    return {
        status: user ? "authenticated" : "unauthenticated",
        user,
        sessionExpired: false,
        login: vi.fn(),
        logout: vi.fn().mockResolvedValue(undefined),
        hasRole: (...roles) => user !== null && roles.includes(user.role),
        hasPermission: (permission) => user?.permissions.includes(permission) ?? false,
        ...overrides,
    }
}

/** Renders the real application routes at the given location with a stubbed auth state. */
export function renderApp(initialEntry: InitialEntry, auth: AuthContextValue) {
    const router = createMemoryRouter(routes, { initialEntries: [initialEntry] })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
        <QueryClientProvider client={queryClient}>
            <AuthContext.Provider value={auth}>
                <RouterProvider router={router} />
            </AuthContext.Provider>
        </QueryClientProvider>,
    )

    return { router }
}

/**
 * Like {@link renderApp}, but starts signed out and becomes authenticated as
 * `user` when login succeeds — mirroring AuthProvider's state transition.
 */
export function renderAppWithLogin(initialEntry: InitialEntry, user: User) {
    const router = createMemoryRouter(routes, { initialEntries: [initialEntry] })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const login = vi.fn()

    function StatefulAuth() {
        const [current, setCurrent] = useState<User | null>(null)
        login.mockImplementation(async () => {
            setCurrent(user)
            return user
        })
        return (
            <AuthContext.Provider value={makeAuth({ user: current, login })}>
                <RouterProvider router={router} />
            </AuthContext.Provider>
        )
    }

    render(
        <QueryClientProvider client={queryClient}>
            <StatefulAuth />
        </QueryClientProvider>,
    )

    return { router, login }
}
