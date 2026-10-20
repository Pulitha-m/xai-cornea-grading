import { useQuery } from "@tanstack/react-query"
import { ShieldCheckIcon } from "lucide-react"
import { listAuditEvents } from "@/api/audit"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"

const ACTION_LABELS: Record<string, string> = {
    CASE_VIEW: "Viewed a case",
    CASE_LIST: "Listed cases",
    CASE_UPDATE: "Changed case details",
    IMAGE_VIEW: "Viewed an image",
    CASE_ANALYSIS: "Ran an analysis",
    RUN_VIEW: "Opened a saved result",
    SEROLOGY_VIEW: "Viewed serology",
    SEROLOGY_UPDATE: "Changed serology",
    SIGNOFF_CREATE: "Signed off a case",
    SIGNOFF_VIEW: "Viewed sign-off notes",
    CANDIDATES_EXPORT: "Listed signed-off corneas",
}

/** Who decrypted or changed sensitive data, and when. Administrators only; the values themselves are never shown. */
export function AuditLogPage() {
    const events = useQuery({ queryKey: ["audit"], queryFn: () => listAuditEvents({ limit: 200 }) })

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <ShieldCheckIcon aria-hidden="true" />
                        Administration
                    </>
                }
                title="Audit log"
                description="Every view of decrypted case data (tissue IDs, images, results, serology, sign-off notes) and every change to it, newest first."
            />
            <Card title="Recent events" description="The 200 most recent events.">
                {events.isPending && <Spinner />}
                {events.isError && <p role="alert" className={alertError}>{events.error.message}</p>}
                {events.isSuccess && events.data.length === 0 && <EmptyState title="No events yet" />}
                {events.isSuccess && events.data.length > 0 && (
                    <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                        <table className="w-full text-sm">
                            <thead className={tableHead}>
                                <tr>
                                    <th className={tableHeaderCell}>When</th>
                                    <th className={tableHeaderCell}>User</th>
                                    <th className={tableHeaderCell}>Action</th>
                                    <th className={tableHeaderCell}>Subject</th>
                                    <th className={tableHeaderCell}>Detail</th>
                                </tr>
                            </thead>
                            <tbody>
                                {events.data.map((e) => (
                                    <tr key={e.id} className={tableRow}>
                                        <td className={`${tableCell} whitespace-nowrap`}>{new Date(e.occurredAt).toLocaleString("en-GB")}</td>
                                        <td className={tableCell}>{e.username}</td>
                                        <td className={tableCell}>{ACTION_LABELS[e.action] ?? e.action}</td>
                                        <td className={`${tableCell} font-mono text-xs`}>
                                            {e.subjectType ? `${e.subjectType} ${e.subjectId?.slice(0, 8) ?? ""}` : "—"}
                                        </td>
                                        <td className={tableCell}>{e.detail ?? "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </>
    )
}
