import { StethoscopeIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { AnalysisPanel } from "@/components/dashboard/AnalysisPanel"
import { PageHeader } from "@/components/dashboard/PageHeader"

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
            {hasPermission("analysis:run") && <AnalysisPanel />}
        </>
    )
}

export function DoctorDashboard() {
    return <ClinicalDashboard title="Clinical review" description="Review corneal assessments for your cases." />
}

export function NurseDashboard() {
    return <ClinicalDashboard title="Clinical workflow" description="Capture and submit corneal images for assessment." />
}
