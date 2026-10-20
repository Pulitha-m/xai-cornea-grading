import { ActivityIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { FollowupPanel } from "@/components/recommendation/FollowupPanel"

export function FollowupPage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <ActivityIcon aria-hidden="true" />
                        Recommendation
                    </>
                }
                title="Post-transplant follow-up"
                description="At the 12-month visit: predicted endothelial cell density at 2, 3 and 5 years, the risk of graft failure and of low ECD, an alert level and when to see the patient next, with the reasons behind it. Decision support only — follow-up decisions rest with the treating clinician."
            />
            <FollowupPanel />
        </>
    )
}
