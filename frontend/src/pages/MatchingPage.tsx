import { UsersIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { MatchingPanel } from "@/components/recommendation/MatchingPanel"

export function MatchingPage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <UsersIcon aria-hidden="true" />
                        Recommendation
                    </>
                }
                title="Recipients & matching"
                description="Ranks the corneas in stock for a recipient request: tissue grade, endothelium, serology, freshness and surgery fit, with the reasons for each position. Positive serology is never ranked. Decision support only — the allocation decision rests with the clinician."
            />
            <MatchingPanel />
        </>
    )
}
