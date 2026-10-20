import { useId, useState, type FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
    DISEASE_FINDINGS,
    GRADES,
    listCaseRuns,
    listSignoffs,
    signOff,
    type DonorCase,
    type RunSummary,
    type SignoffRequest,
} from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"
import { useAuth } from "@/hooks/use-auth"
import { alertError, primaryButton, textInput } from "@/lib/styles"

/** The disease finding suggested by a disease run's headline, in the recommendation module's terms. */
function suggestedFinding(run: RunSummary | undefined): string {
    if (!run) return ""
    if (run.headline.normal === true) return "Normal"
    const detected = Array.isArray(run.headline.detected) ? (run.headline.detected as string[]) : []
    const known = DISEASE_FINDINGS.find((f) => detected.includes(f))
    return known ?? (detected.length > 0 ? "Other" : "")
}

function latestCompleted(runs: RunSummary[] | undefined, module: RunSummary["module"]) {
    return runs?.find((r) => r.module === module && r.status === "completed")
}

/**
 * Specialist sign-off: a doctor confirms the grade, the disease finding and the measurements. Only
 * signed-off values are used for recommendation. Append-only: a correction is a new sign-off.
 */
export function SignoffPanel({ donorCase }: { donorCase: DonorCase }) {
    const { user } = useAuth()
    const canSign = user?.permissions.includes("case:signoff") ?? false
    const signoffs = useQuery({ queryKey: ["case", donorCase.id, "signoffs"], queryFn: () => listSignoffs(donorCase.id) })
    const runs = useQuery({ queryKey: ["case", donorCase.id, "runs"], queryFn: () => listCaseRuns(donorCase.id) })

    return (
        <div className="space-y-6">
            {canSign && runs.isSuccess && <SignoffForm donorCase={donorCase} runs={runs.data} />}
            {!canSign && (
                <p className="rounded-2xl border border-border bg-sunken px-3.5 py-3 text-sm text-muted-foreground">
                    Sign-off is done by a doctor. You can see the sign-offs of this case below.
                </p>
            )}
            <Card title="Sign-offs" description="Newest first. The newest sign-off is the one used for recommendation.">
                {signoffs.isPending && <Spinner />}
                {signoffs.isError && <p role="alert" className={alertError}>{signoffs.error.message}</p>}
                {signoffs.isSuccess && signoffs.data.length === 0 && (
                    <EmptyState title="Not signed off yet" description="A doctor confirms the grade and findings after reviewing the analyses." />
                )}
                {signoffs.isSuccess && signoffs.data.length > 0 && (
                    <ol className="space-y-3">
                        {signoffs.data.map((s, index) => (
                            <li key={s.id} className="rounded-2xl border border-border p-4">
                                <div className="flex flex-wrap items-center gap-2">
                                    <StatusBadge tone={index === 0 ? "success" : "neutral"}>{index === 0 ? "Current" : "Superseded"}</StatusBadge>
                                    <span className="text-sm font-semibold">Grade {s.confirmedGrade} · {s.diseaseFinding}</span>
                                    <span className="text-xs text-muted-foreground">
                                        by {s.signedByName ?? "unknown"} on {new Date(s.createdAt).toLocaleString("en-GB")}
                                    </span>
                                </div>
                                <p className="mt-2 text-sm text-muted-foreground">
                                    ECD {s.ecd?.toLocaleString("en-GB") ?? "—"} cells/mm² · CV {s.cv ?? "—"} % · HEX {s.hexPercent ?? "—"} %
                                </p>
                                {s.notes && <p className="mt-2 text-sm whitespace-pre-wrap">{s.notes}</p>}
                            </li>
                        ))}
                    </ol>
                )}
            </Card>
        </div>
    )
}

function SignoffForm({ donorCase, runs }: { donorCase: DonorCase; runs: RunSummary[] }) {
    const queryClient = useQueryClient()
    const grading = latestCompleted(runs, "grading")
    const disease = latestCompleted(runs, "disease")
    const [grade, setGrade] = useState(typeof grading?.headline.grade === "string" ? grading.headline.grade : "")
    const [finding, setFinding] = useState(suggestedFinding(disease))
    const [ecd, setEcd] = useState(donorCase.details.ecd?.toString() ?? "")
    const [cv, setCv] = useState(donorCase.details.cv?.toString() ?? "")
    const [hex, setHex] = useState(donorCase.details.hexPercent?.toString() ?? "")
    const [notes, setNotes] = useState("")
    const [error, setError] = useState<string | null>(null)
    const ids = { grade: useId(), finding: useId(), ecd: useId(), cv: useId(), hex: useId(), notes: useId() }

    const save = useMutation({
        mutationFn: (request: SignoffRequest) => signOff(donorCase.id, request),
        onSuccess: () => {
            setNotes("")
            void queryClient.invalidateQueries({ queryKey: ["case", donorCase.id] })
        },
    })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        const number = (raw: string) => (raw.trim() === "" ? null : Number(raw))
        const values = { ecd: number(ecd), cv: number(cv), hexPercent: number(hex) }
        if (!grade || !finding) {
            setError("Choose the confirmed grade and disease finding.")
            return
        }
        if (Object.values(values).some((v) => v !== null && !(Number.isFinite(v) && v > 0))
            || (values.hexPercent !== null && values.hexPercent > 100)) {
            setError("Measurements must be greater than 0 (hexagonality at most 100 %).")
            return
        }
        setError(null)
        save.mutate({
            confirmedGrade: grade,
            diseaseFinding: finding,
            ...values,
            notes: notes.trim() || null,
            caseAnalysisId: grading?.caseAnalysisId ?? disease?.caseAnalysisId ?? null,
        })
    }

    const shownError = error ?? (save.isError ? save.error.message : null)

    return (
        <Card
            title="Sign off this case"
            description="Confirm what you accept after reviewing the analyses. Pre-filled from the latest analysis and the case details; change anything you do not agree with."
        >
            <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                    <div>
                        <label htmlFor={ids.grade} className="mb-1.5 block text-sm font-medium">Confirmed grade</label>
                        <select id={ids.grade} value={grade} onChange={(e) => setGrade(e.target.value)} className={textInput}>
                            <option value="">Choose…</option>
                            {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor={ids.finding} className="mb-1.5 block text-sm font-medium">Disease finding</label>
                        <select id={ids.finding} value={finding} onChange={(e) => setFinding(e.target.value)} className={textInput}>
                            <option value="">Choose…</option>
                            {DISEASE_FINDINGS.map((f) => <option key={f} value={f}>{f}</option>)}
                        </select>
                    </div>
                    <NumberField id={ids.ecd} label="ECD (cells/mm²)" value={ecd} onChange={setEcd} />
                    <NumberField id={ids.cv} label="CV (%)" value={cv} onChange={setCv} />
                    <NumberField id={ids.hex} label="HEX (%)" value={hex} onChange={setHex} />
                </div>
                <div>
                    <label htmlFor={ids.notes} className="mb-1.5 block text-sm font-medium">Notes (optional, stored encrypted)</label>
                    <textarea id={ids.notes} value={notes} maxLength={2000} rows={3} onChange={(e) => setNotes(e.target.value)}
                        className={`${textInput} h-auto py-2`} />
                </div>
                {shownError && <p role="alert" className={alertError}>{shownError}</p>}
                <div className="flex items-center gap-3">
                    <button type="submit" disabled={save.isPending} className={primaryButton}>
                        {save.isPending && <Spinner />}
                        Sign off
                    </button>
                    {save.isSuccess && <p role="status" className="text-sm text-success">Signed off.</p>}
                </div>
            </form>
        </Card>
    )
}

function NumberField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div>
            <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>
            <input id={id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} className={textInput} />
        </div>
    )
}
