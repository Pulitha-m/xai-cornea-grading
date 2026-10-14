import { apiRequest } from "@/lib/api-client"
import type { CreateUserRequest, ManagedUser, Role } from "@/types/auth"

export const USERS_QUERY_KEY = ["users"] as const

export function listUsers(): Promise<ManagedUser[]> {
    return apiRequest<ManagedUser[]>("/api/users")
}

export function createUser(request: CreateUserRequest): Promise<ManagedUser> {
    return apiRequest<ManagedUser>("/api/users", { method: "POST", body: request })
}

export function assignRole(userId: number, role: Role): Promise<ManagedUser> {
    return apiRequest<ManagedUser>(`/api/users/${userId}/role`, { method: "PUT", body: { role } })
}

export function setUserEnabled(userId: number, enabled: boolean): Promise<ManagedUser> {
    return apiRequest<ManagedUser>(`/api/users/${userId}/status`, { method: "PATCH", body: { enabled } })
}
