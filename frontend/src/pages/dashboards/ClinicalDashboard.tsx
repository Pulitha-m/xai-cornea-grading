import { Link } from "react-router-dom"
import { ArrowRightIcon, StethoscopeIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { ANALYSIS_PATH, ROLE_LABELS } from "@/lib/roles"
import { primaryLinkButton } from "@/lib/styles"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"

/** Shared layout for clinical roles; the entry points below differ only in copy. */
function ClinicalDashboard({ title, description }: { title: string; description: string }) {
    const { user, hasPermission } = useAuth()

    return (
        <>
            <PageHeader
                eyebrow={
                    user && (
                        <>
                            <StethoscopeIcon aria-hidden="true" />
                            {ROLE_LABELS[user.role]} portal
                        </>
                    )
                }
                title={title}
                description={`Signed in as ${user?.fullName}. ${description}`}
            />
            {hasPermission("analysis:run") && (
                <Card
                    title="Run corneal analysis"
                    description="Cellular analysis, cornea grading, disease screening and a recommendation from one specular microscopy image."
                    actions={
                        <Link to={ANALYSIS_PATH} className={`${primaryLinkButton} gap-2`}>
                            Open workspace
                            <ArrowRightIcon className="size-4" aria-hidden="true" />
                        </Link>
                    }
                >
                    <p className="text-sm text-muted-foreground">
                        Each module reports independently, with its own status and model confidence. Results are decision
                        support for specialist review.
                    </p>
                </Card>
            )}
        </>
    )
}

export function DoctorDashboard() {
    return <ClinicalDashboard title="Clinical review" description="Review corneal assessments for your cases." />
}

export function NurseDashboard() {
    return <ClinicalDashboard title="Clinical workflow" description="Capture and submit corneal images for assessment." />
}
