import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { FullPageSpinner } from "@/components/ui/spinner"

/**
 * Renders child routes only for signed-in users. Others are sent to /login with
 * the requested location preserved so they return there after signing in.
 *
 * This is a UX guard only — the API independently enforces authentication.
 */
export function ProtectedRoute() {
    const { status } = useAuth()
    const location = useLocation()

    if (status === "loading") {
        return <FullPageSpinner label="Checking your session" />
    }

    if (status === "unauthenticated") {
        return <Navigate to="/login" replace state={{ from: location }} />
    }

    return <Outlet />
}
