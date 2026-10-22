import { useState } from "react"
import { ActivityIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { FollowupPanel } from "@/components/recommendation/FollowupPanel"
import { PreviousRuns } from "@/components/recommendation/PreviousRuns"
import { GraftsPanel } from "@/components/transplant/GraftsPanel"
import { ModeSwitch } from "@/components/transplant/ModeSwitch"
import { SHOW_FOLLOWUP_RISK, SHOW_GRAFTS_ON_FOLLOWUP } from "@/lib/feature-flags"

export function FollowupPage() {
    const [mode, setMode] = useState<"grafts" | "manual">("grafts")

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
                description={SHOW_FOLLOWUP_RISK
                    ? "At the 12-month visit: predicted endothelial cell density at 2, 3 and 5 years, the risk of graft failure and of low ECD, an alert level and when to see the patient next, with the reasons behind it. Decision support only — follow-up decisions rest with the treating clinician."
                    : "At the 12-month visit: predicted endothelial cell density at 2, 3 and 5 years, with its likely range and the reasons behind it. Decision support only — follow-up decisions rest with the treating clinician."}
            />
            {SHOW_GRAFTS_ON_FOLLOWUP && <ModeSwitch label="Grafts to follow up" value={mode} onChange={setMode} options={[
                { value: "grafts", label: "Grafts from donor cases" },
                { value: "manual", label: "Enter values by hand" },
            ]} />}
            {SHOW_GRAFTS_ON_FOLLOWUP && mode === "grafts" ? <GraftsPanel /> : <FollowupPanel />}
            <div className="mt-6">
                <PreviousRuns kind="followup" />
            </div>
        </>
    )
}
