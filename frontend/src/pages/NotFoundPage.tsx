import { Link } from "react-router-dom"
import { CompassIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { dashboardPathFor } from "@/lib/roles"
import { primaryButton } from "@/lib/styles"
import { BrandMark } from "@/components/brand/BrandMark"
import { StatusPage } from "@/components/layout/StatusPage"

export function NotFoundPage() {
    const { user } = useAuth()

    return (
        <div className="flex min-h-svh flex-col items-center justify-center gap-8 bg-background px-4 py-12">
            <BrandMark className="h-12" />
            <StatusPage
                icon={<CompassIcon aria-hidden="true" />}
                code="404"
                title="Page not found"
                description="The page you are looking for does not exist or may have been moved."
                action={
                    <Link to={user ? dashboardPathFor(user.role) : "/login"} className={primaryButton}>
                        {user ? "Back to your dashboard" : "Go to sign in"}
                    </Link>
                }
            />
        </div>
    )
}
