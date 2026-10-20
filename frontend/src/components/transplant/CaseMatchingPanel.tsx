import { useId, useState, type FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { listCandidates } from "@/api/cases"
import type { MatchRequestInfo, TissueGrade } from "@/api/recommendation"
import {
    allocateGraft,
    INDICATIONS,
    matchFromCases,
    PROCEDURES,
    type CaseMatchResponse,
    type Procedure,
} from "@/api/transplants"
import { Card } from "@/components/dashboard/PageHeader"
import { MatchingResults } from "@/components/recommendation/MatchingResults"
import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/hooks/use-auth"
import { GRADES, SURGERIES } from "@/lib/matching-form"
import { CASES_PATH, FOLLOWUP_PATH } from "@/lib/roles"
import { alertError, primaryButton, textInput } from "@/lib/styles"

/**
 * Ranks the signed-off corneas in stock for a recipient request, with their confirmed values; a doctor
 * then allocates one, which creates its graft for post-transplant follow-up and takes it out of stock.
 */
export function CaseMatchingPanel() {
    const ids = useId()
    const [requestId, setRequestId] = useState("")
    const [requestedGrade, setRequestedGrade] = useState<TissueGrade>("A")
    const [surgeryType, setSurgeryType] = useState("PK")
    const [urgency, setUrgency] = useState<NonNullable<MatchRequestInfo["urgency"]>>("Routine")
    const [method, setMethod] = useState<"ml" | "mcda">("ml")
    const [problem, setProblem] = useState<string | null>(null)

    const stock = useQuery({ queryKey: ["cases", "candidates"], queryFn: listCandidates })
    const match = useMutation({ mutationFn: matchFromCases })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        if (!requestId.trim()) {
            setProblem("Enter the request ID.")
            return
        }
        setProblem(null)
        match.mutate({ request: { requestId: requestId.trim(), requestedGrade, surgeryType, urgency }, method })
    }

    const select = <T extends string>(id: string, label: string, value: T, options: readonly T[], onChange: (v: T) => void,
        names: Partial<Record<T, string>> = {}) => (
        <div>
            <label htmlFor={`${ids}-${id}`} className="mb-1.5 block text-sm font-medium">{label}</label>
            <select id={`${ids}-${id}`} value={value} className={textInput}
                onChange={(e) => { onChange(e.target.value as T); match.reset() }}>
                {options.map((o) => <option key={o} value={o}>{names[o] ?? o}</option>)}
            </select>
        </div>
    )

    const result = match.data

    return (
        <div className="space-y-6">
            <Card
                title="Recipient request"
                description="Ranks the signed-off corneas in stock, using the values the specialist confirmed. Allocated corneas and corneas stored longer than 14 days are not in stock."
            >
                <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-5">
                        <div>
                            <label htmlFor={`${ids}-request`} className="mb-1.5 block text-sm font-medium">Request ID</label>
                            <input id={`${ids}-request`} value={requestId} placeholder="Q0012" className={textInput}
                                onChange={(e) => { setRequestId(e.target.value); match.reset() }} />
                        </div>
                        {select("grade", "Requested grade", requestedGrade, GRADES, setRequestedGrade)}
                        {select("surgery", "Surgery", surgeryType, SURGERIES, setSurgeryType)}
                        {select("urgency", "Urgency", urgency, ["Routine", "Emergency"] as const, setUrgency)}
                        {select("method", "Ranking method", method, ["ml", "mcda"] as const, setMethod,
                            { ml: "ML ranker (learned)", mcda: "MCDA (clinician weights)" })}
                    </div>
                    <p className="text-sm text-muted-foreground">
                        {stock.isSuccess
                            ? `${stock.data.length} signed-off ${stock.data.length === 1 ? "cornea" : "corneas"} in stock.`
                            : "Loading the corneas in stock…"}
                    </p>
                    {problem && <p role="alert" className={alertError}>{problem}</p>}
                    {match.isError && <p role="alert" className={alertError}>{match.error.message}</p>}
                    <button type="submit" disabled={match.isPending} className={primaryButton}>
                        {match.isPending ? <><Spinner /> Ranking…</> : "Rank corneas in stock"}
                    </button>
                </form>
            </Card>

            {result && (
                <>
                    {result.notInStock > 0 && (
                        <p className="rounded-2xl border border-border bg-sunken px-3.5 py-3 text-sm text-muted-foreground">
                            {result.considered} considered; {result.notInStock} other signed-off{" "}
                            {result.notInStock === 1 ? "cornea is" : "corneas are"} no longer in stock (allocated or stored over 14 days).
                        </p>
                    )}
                    <MatchingResults
                        result={result.match}
                        labelFor={(recordId) => result.tissueIds[recordId]
                            ? <Link to={`${CASES_PATH}/${recordId}`} className="font-mono text-accent hover:underline">{result.tissueIds[recordId]}</Link>
                            : recordId}
                    />
                    <AllocateCard result={result} surgeryType={surgeryType} />
                </>
            )}
        </div>
    )
}

function AllocateCard({ result, surgeryType }: { result: CaseMatchResponse; surgeryType: string }) {
    const { user } = useAuth()
    const queryClient = useQueryClient()
    const ids = useId()
    const ranked = result.match.ranked
    const [caseId, setCaseId] = useState(ranked[0]?.recordId ?? "")
    const [procedure, setProcedure] = useState<Procedure>(
        (PROCEDURES as readonly string[]).includes(surgeryType) ? (surgeryType as Procedure) : "PK")
    const [indication, setIndication] = useState(INDICATIONS[0])
    const [surgeryDate, setSurgeryDate] = useState("")

    const allocate = useMutation({
        mutationFn: allocateGraft,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: ["cases"] })
            void queryClient.invalidateQueries({ queryKey: ["grafts"] })
        },
    })

    if (!user?.permissions.includes("case:signoff") || ranked.length === 0) return null

    if (allocate.isSuccess) {
        const graft = allocate.data
        return (
            <Card title="Allocated">
                <p role="status" className="text-sm">
                    Tissue <Link to={`${CASES_PATH}/${graft.caseId}`} className="font-mono text-accent hover:underline">{graft.tissueId}</Link>{" "}
                    is allocated to request {graft.requestId} ({graft.procedure}). Record its visits under{" "}
                    <Link to={FOLLOWUP_PATH} className="text-accent hover:underline">Post-transplant follow-up</Link>.
                </p>
            </Card>
        )
    }

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        allocate.mutate({
            caseId, requestId: result.match.requestId, procedure, indication,
            surgeryDate: surgeryDate || null, matchRunId: result.match.analysisId,
        })
    }

    return (
        <Card title="Allocate a cornea" description={`Allocates the chosen cornea to request ${result.match.requestId}. This is the clinician's decision; the ranking only supports it.`}>
            <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                <div className="grid gap-4 sm:grid-cols-4">
                    <div>
                        <label htmlFor={`${ids}-cornea`} className="mb-1.5 block text-sm font-medium">Cornea</label>
                        <select id={`${ids}-cornea`} value={caseId} onChange={(e) => setCaseId(e.target.value)} className={textInput}>
                            {ranked.map((c) => (
                                <option key={c.recordId} value={c.recordId}>
                                    #{c.rank} {result.tissueIds[c.recordId] ?? c.recordId} ({c.grade ?? "–"})
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label htmlFor={`${ids}-procedure`} className="mb-1.5 block text-sm font-medium">Procedure</label>
                        <select id={`${ids}-procedure`} value={procedure} onChange={(e) => setProcedure(e.target.value as Procedure)} className={textInput}>
                            {PROCEDURES.map((p) => <option key={p}>{p}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor={`${ids}-indication`} className="mb-1.5 block text-sm font-medium">Indication</label>
                        <select id={`${ids}-indication`} value={indication} onChange={(e) => setIndication(e.target.value)} className={textInput}>
                            {INDICATIONS.map((i) => <option key={i}>{i}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor={`${ids}-date`} className="mb-1.5 block text-sm font-medium">Surgery date</label>
                        <input id={`${ids}-date`} type="date" value={surgeryDate} onChange={(e) => setSurgeryDate(e.target.value)} className={textInput} />
                    </div>
                </div>
                {allocate.isError && <p role="alert" className={alertError}>{allocate.error.message}</p>}
                <button type="submit" disabled={allocate.isPending || !caseId} className={primaryButton}>
                    {allocate.isPending && <Spinner />}
                    Allocate
                </button>
            </form>
        </Card>
    )
}
