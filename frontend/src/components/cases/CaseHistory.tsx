import { Fragment, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getCaseRun, listCaseRuns, MODULE_LABELS, type CaseImage, type RunSummary } from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"

const STATUS_TONES: Record<string, StatusTone> = {
    completed: "success",
    partial: "warning",
    input_check_failed: "warning",
    rejected: "danger",
    failed: "danger",
}

/** The main values of a saved run, for the history list. */
function headline(run: RunSummary): string {
    const h = run.headline
    const number = (v: unknown, digits = 0) => (typeof v === "number" ? v.toLocaleString("en-GB", { maximumFractionDigits: digits }) : "—")
    switch (run.module) {
        case "grading":
        case "combined":
            return h.grade ? `Grade ${String(h.grade)}` : "—"
        case "cellular":
            return `ECD ${number(h.ecd)} · CV ${number(h.cv, 1)} % · HEX ${number(h.hex, 1)} %${h.reliable === false ? " · not reliable" : ""}`
        case "disease": {
            const detected = Array.isArray(h.detected) ? (h.detected as string[]) : []
            if (h.normal === true) return "No disease detected"
            return detected.length > 0 ? `Detected: ${detected.join(", ")}` : "—"
        }
    }
}

/** Every saved run of the case, across modules, newest first. Any clinician on the case can see them. */
export function CaseHistory({ caseId, images }: { caseId: string; images: CaseImage[] }) {
    const runs = useQuery({ queryKey: ["case", caseId, "runs"], queryFn: () => listCaseRuns(caseId) })
    const [open, setOpen] = useState<string | null>(null)
    const imageNumber = (id: string) => {
        const index = images.findIndex((i) => i.id === id)
        return index === -1 ? "—" : `Image ${images.length - index}`
    }

    return (
        <Card title="History" description="Every analysis run on this case, including rejected and failed attempts.">
            {runs.isPending && <Spinner />}
            {runs.isError && <p role="alert" className={alertError}>{runs.error.message}</p>}
            {runs.isSuccess && runs.data.length === 0 && (
                <EmptyState title="No analyses yet" description="Results appear here once an analysis has run on this case." />
            )}
            {runs.isSuccess && runs.data.length > 0 && (
                <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>When</th>
                                <th className={tableHeaderCell}>Module</th>
                                <th className={tableHeaderCell}>Status</th>
                                <th className={tableHeaderCell}>Result</th>
                                <th className={tableHeaderCell}>Image</th>
                                <th className={tableHeaderCell}><span className="sr-only">Details</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {runs.data.map((run) => (
                                <Fragment key={run.id}>
                                    <tr className={tableRow}>
                                        <td className={tableCell}>{new Date(run.createdAt).toLocaleString("en-GB")}</td>
                                        <td className={tableCell}>{MODULE_LABELS[run.module]}</td>
                                        <td className={tableCell}>
                                            <StatusBadge tone={STATUS_TONES[run.status] ?? "neutral"}>{run.status.replaceAll("_", " ")}</StatusBadge>
                                            {run.errorCode && <span className="ml-2 font-mono text-2xs text-muted-foreground">{run.errorCode}</span>}
                                        </td>
                                        <td className={tableCell}>{headline(run)}</td>
                                        <td className={tableCell}>{imageNumber(run.imageId)}</td>
                                        <td className={tableCell}>
                                            <button type="button" className="text-sm font-medium text-accent hover:underline"
                                                aria-expanded={open === run.id}
                                                onClick={() => setOpen(open === run.id ? null : run.id)}>
                                                {open === run.id ? "Hide" : "Details"}
                                            </button>
                                        </td>
                                    </tr>
                                    {open === run.id && (
                                        <tr>
                                            <td colSpan={6} className={tableCell}>
                                                <RunDetailView caseId={caseId} run={run} />
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    )
}

function RunDetailView({ caseId, run }: { caseId: string; run: RunSummary }) {
    const detail = useQuery({
        queryKey: ["case", caseId, "run", run.module, run.id],
        queryFn: () => getCaseRun(caseId, run.module, run.id),
    })
    if (detail.isPending) return <Spinner />
    if (detail.isError) return <p role="alert" className={alertError}>{detail.error.message}</p>
    return (
        <div className="grid gap-4 lg:grid-cols-2">
            <section>
                <h3 className="mb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">Inputs</h3>
                <pre className="max-h-72 overflow-auto rounded-2xl bg-sunken p-3 text-xs">
                    {detail.data.inputs ? JSON.stringify(detail.data.inputs, null, 2) : "No inputs (image only)."}
                </pre>
            </section>
            <section>
                <h3 className="mb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">Saved result</h3>
                <pre className="max-h-72 overflow-auto rounded-2xl bg-sunken p-3 text-xs">
                    {detail.data.result ? JSON.stringify(detail.data.result, null, 2) : "No result: the run did not complete."}
                </pre>
            </section>
        </div>
    )
}
