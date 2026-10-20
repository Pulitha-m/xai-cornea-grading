import { useState, type FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getSerology, SEROLOGY_TESTS, updateSerology, type Serology, type SerologyResult } from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"
import { alertError, primaryButton, textInput } from "@/lib/styles"

type SerologyInputs = Record<(typeof SEROLOGY_TESTS)[number]["key"], SerologyResult | "">

function clearBadge(clear: boolean | null) {
    if (clear === true) return <StatusBadge tone="success">All negative</StatusBadge>
    if (clear === false) return <StatusBadge tone="danger">Positive result</StatusBadge>
    return <StatusBadge tone="warning">Incomplete</StatusBadge>
}

/**
 * Serology results, doctors only. They are stored encrypted and fetched only on request, because
 * every read is recorded in the audit log. A positive result excludes the cornea from recommendation.
 */
export function SerologyCard({ caseId }: { caseId: string }) {
    const [shown, setShown] = useState(false)
    const serology = useQuery({
        queryKey: ["case", caseId, "serology"],
        queryFn: () => getSerology(caseId),
        enabled: shown,
        gcTime: 0,
    })

    return (
        <Card
            title="Serology"
            description="Doctors only. Stored encrypted; each view and change is recorded in the audit log."
            actions={serology.data && clearBadge(serology.data.serologyClear)}
        >
            {!shown && (
                <button type="button" onClick={() => setShown(true)} className={primaryButton}>Show serology</button>
            )}
            {shown && serology.isPending && <Spinner />}
            {serology.isError && <p role="alert" className={alertError}>{serology.error.message}</p>}
            {serology.isSuccess && <SerologyForm caseId={caseId} serology={serology.data} />}
        </Card>
    )
}

function SerologyForm({ caseId, serology }: { caseId: string; serology: Serology }) {
    const queryClient = useQueryClient()
    const [inputs, setInputs] = useState<SerologyInputs>({
        hiv: serology.hiv ?? "", hbv: serology.hbv ?? "", hcv: serology.hcv ?? "", syphilis: serology.syphilis ?? "",
    })
    const save = useMutation({
        mutationFn: () => updateSerology(caseId, {
            hiv: inputs.hiv || null, hbv: inputs.hbv || null, hcv: inputs.hcv || null, syphilis: inputs.syphilis || null,
        }),
        onSuccess: (updated) => queryClient.setQueryData(["case", caseId, "serology"], updated),
    })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        save.mutate()
    }

    return (
        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {SEROLOGY_TESTS.map((test) => (
                    <label key={test.key} className="block text-sm font-medium">
                        <span className="mb-1.5 block">{test.label}</span>
                        <select
                            value={inputs[test.key]}
                            onChange={(e) => {
                                setInputs((current) => ({ ...current, [test.key]: e.target.value as SerologyResult | "" }))
                                save.reset()
                            }}
                            className={textInput}
                        >
                            <option value="">Not recorded</option>
                            <option value="Negative">Negative</option>
                            <option value="Positive">Positive</option>
                            <option value="Unknown">Unknown</option>
                        </select>
                    </label>
                ))}
            </div>
            {save.isError && <p role="alert" className={alertError}>{save.error.message}</p>}
            <div className="flex items-center gap-3">
                <button type="submit" disabled={save.isPending} className={primaryButton}>
                    {save.isPending && <Spinner />}
                    Save serology
                </button>
                {save.isSuccess && <p role="status" className="text-sm text-success">Serology saved.</p>}
            </div>
        </form>
    )
}
