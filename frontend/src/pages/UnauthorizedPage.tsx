import { Link } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { dashboardPathFor } from "@/lib/roles"
import { primaryButton } from "@/lib/styles"
import { StatusPage } from "@/components/layout/StatusPage"
import { ShieldIcon } from "@/components/ui/icons"

export function UnauthorizedPage() {
    const { user } = useAuth()

    return (
        <StatusPage
            icon={<ShieldIcon className="size-6" />}
            code="403"
            title="Access denied"
            description="Your role does not have permission to view this page. If you believe this is a mistake, contact your administrator."
            action={
                <Link to={user ? dashboardPathFor(user.role) : "/login"} className={primaryButton}>
                    {user ? "Go to your dashboard" : "Sign in"}
                </Link>
            }
        />
    )
}
