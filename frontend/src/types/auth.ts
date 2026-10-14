export const ROLES = ["ADMIN", "MANAGER", "DOCTOR", "NURSE", "SUPPORT_STAFF"] as const

export type Role = (typeof ROLES)[number]

/** Permission strings granted by the backend. Used only to shape the UI; the API enforces them. */
export type Permission = "users:read" | "users:manage" | "roles:assign" | "analysis:run"

export interface User {
    id: number
    username: string
    email: string
    fullName: string
    role: Role
    permissions: Permission[]
}

export interface AuthResponse {
    accessToken: string
    tokenType: "Bearer"
    expiresIn: number
    expiresAt: string
    user: User
}

export interface LoginRequest {
    identifier: string
    password: string
    rememberMe: boolean
}

export interface ManagedUser {
    id: number
    username: string
    email: string
    fullName: string
    role: Role
    enabled: boolean
    lastLoginAt: string | null
    createdAt: string
}

export interface CreateUserRequest {
    username: string
    email: string
    fullName: string
    role: Role
    password: string
}
