import { Navigate } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { dashboardPathFor } from "@/lib/roles"

/** Sends a signed-in user from "/" to their role's dashboard. */
export function HomeRedirect() {
    const { user } = useAuth()
    return user ? <Navigate to={dashboardPathFor(user.role)} replace /> : null
}
