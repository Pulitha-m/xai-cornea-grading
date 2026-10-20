import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { listGrafts } from "@/api/transplants"
import { Card } from "@/components/dashboard/PageHeader"
import { GraftFollowupPanel } from "@/components/transplant/GraftFollowupPanel"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { MATCHING_PATH } from "@/lib/roles"
import { alertError } from "@/lib/styles"

/** The case's transplant: its graft (if allocated), visits and follow-up recommendations. */
export function CaseTransplantTab({ caseId, signedOff }: { caseId: string; signedOff: boolean }) {
    const grafts = useQuery({ queryKey: ["grafts", { caseId }], queryFn: () => listGrafts(caseId) })

    if (grafts.isPending) return <Spinner />
    if (grafts.isError) return <p role="alert" className={alertError}>{grafts.error.message}</p>
    const graft = grafts.data[0]
    if (!graft) {
        return (
            <Card title="Transplant">
                <EmptyState
                    title="Not allocated"
                    description={signedOff
                        ? "This cornea is signed off and can be ranked for a recipient request."
                        : "Sign off the case first; only signed-off corneas can be allocated."}
                    action={signedOff ? <Link to={MATCHING_PATH} className="text-sm font-medium text-accent hover:underline">Go to Recipients & matching</Link> : undefined}
                />
            </Card>
        )
    }
    return <GraftFollowupPanel graft={graft} />
}
