import { Outlet } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { UnauthorizedPage } from "@/pages/UnauthorizedPage"
import type { Role } from "@/types/auth"

/**
 * Renders child routes only for the allowed roles; otherwise shows the
 * access-denied page without rendering any of the protected content.
 * Must be nested inside {@link ProtectedRoute}.
 */
export function RoleGuard({ allow }: { allow: Role[] }) {
    const { hasRole } = useAuth()

    if (!hasRole(...allow)) {
        return <UnauthorizedPage />
    }

    return <Outlet />
}
