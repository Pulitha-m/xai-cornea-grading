import { Link } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { dashboardPathFor } from "@/lib/roles"
import { primaryLinkButton } from "@/lib/styles"
import { StatusPage } from "@/components/layout/StatusPage"

export function NotFoundPage() {
    const { user } = useAuth()

    return (
        <div className="min-h-svh bg-background px-4">
            <StatusPage
                code="404"
                title="Page not found"
                description="The page you are looking for does not exist or may have been moved."
                action={
                    <Link to={user ? dashboardPathFor(user.role) : "/login"} className={primaryLinkButton}>
                        {user ? "Back to your dashboard" : "Go to sign in"}
                    </Link>
                }
            />
        </div>
    )
}
