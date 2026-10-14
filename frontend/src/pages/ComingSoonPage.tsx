import { HourglassIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { StatusBadge } from "@/components/ui/status-badge"

/** Placeholder for a planned module; deliberately shows no sample data. */
export function ComingSoonPage({ title, description }: { title: string; description: string }) {
    return (
        <>
            <PageHeader title={title} description={description}>
                <StatusBadge tone="warning">Coming soon</StatusBadge>
            </PageHeader>
            <EmptyState
                icon={<HourglassIcon />}
                title="This module is not available yet"
                description="It will appear here once it is connected to the eye bank's records. No sample or placeholder data is shown in the meantime."
            />
        </>
    )
}
