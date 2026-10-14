import { Outlet } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { UnauthorizedPage } from "@/pages/UnauthorizedPage"
import type { Permission, Role } from "@/types/auth"

/**
 * Renders child routes only for the allowed roles (and, if given, users holding
 * `permission`); otherwise shows the access-denied page without rendering any
 * of the protected content. Must be nested inside {@link ProtectedRoute}.
 */
export function RoleGuard({ allow, permission }: { allow: Role[]; permission?: Permission }) {
    const { hasRole, hasPermission } = useAuth()

    if (!hasRole(...allow) || (permission !== undefined && !hasPermission(permission))) {
        return <UnauthorizedPage />
    }

    return <Outlet />
}
