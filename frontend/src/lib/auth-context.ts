import { createContext } from "react"
import type { LoginRequest, Permission, Role, User } from "@/types/auth"

export type AuthStatus = "loading" | "authenticated" | "unauthenticated"

export interface AuthContextValue {
    status: AuthStatus
    user: User | null
    /** Set when the user was signed out because the session could not be renewed. */
    sessionExpired: boolean
    login: (request: LoginRequest) => Promise<User>
    logout: () => Promise<void>
    hasRole: (...roles: Role[]) => boolean
    hasPermission: (permission: Permission) => boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)
