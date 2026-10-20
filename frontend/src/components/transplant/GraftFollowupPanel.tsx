import { useId, useState, type FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
    getGraftFollowup,
    listGraftFollowups,
    recordGraftVisit,
    runGraftFollowup,
    updateGraft,
    VISIT_MONTHS,
    type FollowupSummary,
    type Graft,
    type GraftFollowup,
} from "@/api/transplants"
import { Card } from "@/components/dashboard/PageHeader"
import { FollowupResults } from "@/components/recommendation/FollowupResults"
import { Field } from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { CASES_PATH } from "@/lib/roles"
import { alertError, alertWarning, primaryButton, textInput } from "@/lib/styles"

const ALERT_TONES: Record<string, StatusTone> = { green: "success", amber: "warning", red: "danger" }

/**
 * One graft's follow-up: its donor and baseline values (from the sign-off, else the case details), the
 * 3-, 6- and 12-month visits, and the follow-up recommendation made from them, with earlier ones.
 */
export function GraftFollowupPanel({ graft }: { graft: Graft }) {
    const queryClient = useQueryClient()
    const refresh = () => {
        void queryClient.invalidateQueries({ queryKey: ["grafts"] })
        void queryClient.invalidateQueries({ queryKey: ["graft", graft.id] })
    }
    const history = useQuery({ queryKey: ["graft", graft.id, "followups"], queryFn: () => listGraftFollowups(graft.id) })
    const run = useMutation({ mutationFn: () => runGraftFollowup(graft.id), onSuccess: refresh })
    const rejection = useMutation({
        mutationFn: (value: boolean) => updateGraft(graft.id, { rejectionBy12m: value }),
        onSuccess: refresh,
    })
    const [shown, setShown] = useState<string | null>(null)

    return (
        <div className="space-y-6">
            <Card
                title={`Graft of tissue ${graft.tissueId}`}
                description={`Request ${graft.requestId} · ${graft.procedure} · ${graft.indication}${graft.surgeryDate ? ` · surgery ${new Date(graft.surgeryDate).toLocaleDateString("en-GB")}` : ""}`}
                actions={<Link to={`${CASES_PATH}/${graft.caseId}`} className="text-sm font-medium text-accent hover:underline">Open case</Link>}
            >
                <dl className="grid gap-4 sm:grid-cols-4">
                    <Field label="Donor age" value={graft.donorAge} unit="years" />
                    <Field label="Baseline ECD" value={graft.baselineEcd?.toLocaleString("en-GB")} unit="cells/mm²" />
                    <Field label="Baseline CV" value={graft.baselineCv} unit="%" />
                    <Field label="Baseline HEX" value={graft.baselineHex} unit="%" />
                </dl>
                <label className="mt-4 flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={graft.rejectionBy12m === true} disabled={rejection.isPending}
                        onChange={(e) => rejection.mutate(e.target.checked)} />
                    A rejection episode occurred in the first year
                </label>
            </Card>

            <Card title="Follow-up visits" description="Specular microscopy after surgery. The 3-month visit may be missing; the 6- and 12-month visits are needed.">
                <div className="space-y-3">
                    {VISIT_MONTHS.map((month) => (
                        <VisitForm key={`${month}-${graft.visits.find((v) => v.month === month)?.ecd ?? ""}`} graft={graft} month={month} onSaved={refresh} />
                    ))}
                </div>
            </Card>

            <Card title="Follow-up recommendation" description="Predicted ECD, risk of graft failure and low ECD, an alert level and the next visit. Decision support only.">
                {graft.missing.length > 0 && (
                    <p className={`mb-4 ${alertWarning}`}>Still needed: {graft.missing.join(", ")}.</p>
                )}
                {run.isError && <p role="alert" className={`mb-4 ${alertError}`}>{run.error.message}</p>}
                <button type="button" onClick={() => run.mutate()} disabled={run.isPending || graft.missing.length > 0} className={primaryButton}>
                    {run.isPending && <Spinner />}
                    Get follow-up recommendation
                </button>
                {history.isSuccess && history.data.length > 0 && (
                    <ul className="mt-5 space-y-2">
                        {history.data.map((f) => (
                            <FollowupRow key={f.runId} summary={f} open={shown === f.runId}
                                onToggle={() => setShown(shown === f.runId ? null : f.runId)} />
                        ))}
                    </ul>
                )}
            </Card>

            {run.isSuccess && <FollowupReport followup={run.data} />}
            {shown && <SavedFollowup graftId={graft.id} runId={shown} />}
        </div>
    )
}

function VisitForm({ graft, month, onSaved }: { graft: Graft; month: 3 | 6 | 12; onSaved: () => void }) {
    const ids = useId()
    const existing = graft.visits.find((v) => v.month === month)
    const [values, setValues] = useState({
        ecd: existing?.ecd.toString() ?? "", cv: existing?.cv.toString() ?? "", hex: existing?.hex.toString() ?? "",
        visitDate: existing?.visitDate ?? "",
    })
    const [error, setError] = useState<string | null>(null)
    const save = useMutation({
        mutationFn: (visit: { ecd: number; cv: number; hex: number; visitDate: string | null }) => recordGraftVisit(graft.id, month, visit),
        onSuccess: onSaved,
    })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        const [ecd, cv, hex] = [values.ecd, values.cv, values.hex].map((v) => Number(v.trim()))
        if ([values.ecd, values.cv, values.hex].some((v) => v.trim() === "") || ![ecd, cv, hex].every(Number.isFinite)
            || ecd <= 0 || ecd > 5000 || cv < 0 || cv > 100 || hex < 0 || hex > 100) {
            setError("Enter ECD (up to 5000), CV and HEX (0–100 %).")
            return
        }
        setError(null)
        save.mutate({ ecd, cv, hex, visitDate: values.visitDate || null })
    }

    const input = (key: keyof typeof values, label: string, type = "text") => (
        <div>
            <label htmlFor={`${ids}-${key}`} className="mb-1 block text-xs font-medium text-muted-foreground">{label}</label>
            <input id={`${ids}-${key}`} type={type} inputMode={type === "text" ? "decimal" : undefined} value={values[key]}
                onChange={(e) => { setValues((v) => ({ ...v, [key]: e.target.value })); save.reset() }} className={textInput} />
        </div>
    )

    return (
        <form onSubmit={handleSubmit} noValidate aria-label={`${month}-month visit`}
            className="grid items-end gap-3 rounded-2xl border border-border p-3 sm:grid-cols-[6rem_1fr_1fr_1fr_1fr_auto]">
            <p className="text-sm font-semibold">{month} months{existing && <span className="ml-1 text-success" aria-label="recorded">✓</span>}</p>
            {input("ecd", "ECD (cells/mm²)")}
            {input("cv", "CV (%)")}
            {input("hex", "HEX (%)")}
            {input("visitDate", "Visit date", "date")}
            <button type="submit" disabled={save.isPending} className="h-10 rounded-full border border-border px-4 text-sm font-medium hover:bg-sunken">
                {save.isPending ? <Spinner /> : "Save"}
            </button>
            {(error || save.isError) && (
                <p role="alert" className={`sm:col-span-6 ${alertError}`}>{error ?? save.error?.message}</p>
            )}
        </form>
    )
}

function FollowupRow({ summary, open, onToggle }: { summary: FollowupSummary; open: boolean; onToggle: () => void }) {
    return (
        <li className="flex flex-wrap items-center gap-3 text-sm">
            <span>{new Date(summary.createdAt).toLocaleString("en-GB")}</span>
            {summary.alert
                ? <StatusBadge tone={ALERT_TONES[summary.alert] ?? "neutral"}>Alert: {summary.alert}</StatusBadge>
                : <StatusBadge tone="danger">{summary.status}</StatusBadge>}
            {summary.nextVisitMonths !== null && <span className="text-muted-foreground">next visit in {summary.nextVisitMonths} months</span>}
            {summary.status === "completed" && (
                <button type="button" onClick={onToggle} aria-expanded={open} className="font-medium text-accent hover:underline">
                    {open ? "Hide report" : "View report"}
                </button>
            )}
        </li>
    )
}

function SavedFollowup({ graftId, runId }: { graftId: string; runId: string }) {
    const saved = useQuery({ queryKey: ["graft", graftId, "followup", runId], queryFn: () => getGraftFollowup(graftId, runId) })
    if (saved.isPending) return <Spinner />
    if (saved.isError) return <p role="alert" className={alertError}>{saved.error.message}</p>
    return <FollowupReport followup={saved.data} />
}

function FollowupReport({ followup }: { followup: GraftFollowup }) {
    if (!followup.result || !followup.request) {
        return <p className={alertError}>This recommendation has no saved report.</p>
    }
    return <FollowupResults result={followup.result} request={followup.request} />
}
