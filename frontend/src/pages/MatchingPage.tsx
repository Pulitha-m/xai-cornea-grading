import { useState } from "react"
import { UsersIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { MatchingPanel } from "@/components/recommendation/MatchingPanel"
import { PreviousRuns } from "@/components/recommendation/PreviousRuns"
import { CaseMatchingPanel } from "@/components/transplant/CaseMatchingPanel"
import { ModeSwitch } from "@/components/transplant/ModeSwitch"
import { useAuth } from "@/hooks/use-auth"
import { SHOW_STOCK_ON_MATCHING } from "@/lib/feature-flags"

export function MatchingPage() {
    const { user } = useAuth()
    // Signed-off corneas carry serology status, so only doctors rank them; anyone may enter corneas by hand.
    const fromCases = SHOW_STOCK_ON_MATCHING && (user?.permissions.includes("serology:access") ?? false)
    const [mode, setMode] = useState<"cases" | "manual">(fromCases ? "cases" : "manual")

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
                description="Ranks the corneas in stock for a recipient request: tissue grade, endothelium, serology, freshness and surgery fit, with the reasons for each position. Corneas with positive serology are excluded by a safety rule. Decision support only — the allocation decision rests with the clinician."
            />
            {fromCases && (
                <ModeSwitch label="Corneas to rank" value={mode} onChange={setMode} options={[
                    { value: "cases", label: "Signed-off corneas in stock" },
                    { value: "manual", label: "Enter corneas by hand" },
                ]} />
            )}
            {mode === "cases" ? <CaseMatchingPanel /> : <MatchingPanel />}
            <div className="mt-6">
                <PreviousRuns kind="match" />
            </div>
        </>
    )
}
