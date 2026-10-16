import { useState, type FormEvent } from "react"
import { useAnalysis } from "@/hooks/use-analysis"
import { parseEcd } from "@/lib/ecd"
import type { AnalyzeResponse, GradingResult } from "@/api/analysis"

const GRADE_ORDER = ["A+", "A", "B"]

function formatBand(grading: GradingResult) {
    const lower = grading.ecdBand?.lowerExclusive
    const upper = grading.ecdBand?.upperInclusive
    if (lower == null && upper != null) return `ECD ≤ ${upper}`
    if (lower != null && upper == null) return `ECD > ${lower}`
    return `${lower} < ECD ≤ ${upper}`
}

function GradingPanel({ grading }: { grading: GradingResult }) {
    if (grading.status === "failed") {
        return (
            <p role="alert" className="text-red-600">
                Grading failed: {grading.error}
            </p>
        )
    }

    if (grading.status === "review_required") {
        return (
            <div role="status" className="rounded-md border border-amber-400 bg-amber-50 p-4">
                <p className="font-semibold">No automated grade — manual grading required</p>
                <p className="mt-1 text-sm">{grading.message}</p>
            </div>
        )
    }

    const distribution = grading.bandDistribution ?? {}

    return (
        <div className="space-y-4">
            <div className="flex items-baseline gap-3">
                <span className="text-sm text-neutral-600">ECD-based grade</span>
                <span data-testid="grade" className="text-4xl font-bold">
                    {grading.grade}
                </span>
            </div>

            <p className="rounded-md border border-amber-400 bg-amber-50 p-3 text-sm">
                Decision support only. {grading.message}
            </p>

            {grading.reviewRequired && (
                <p role="alert" className="text-sm font-semibold text-amber-700">
                    Review carefully: this ECD is outside the range seen in training data.
                </p>
            )}

            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-neutral-600">ECD used</dt>
                <dd>{grading.ecdUsed} cells/mm²</dd>
                <dt className="text-neutral-600">ECD band</dt>
                <dd>{formatBand(grading)}</dd>
            </dl>

            <div>
                <p className="text-sm text-neutral-600">
                    Recorded grades of the {grading.bandTrainingTissues} training tissues in this ECD band
                    (not model confidence):
                </p>
                <ul className="mt-1 text-sm">
                    {GRADE_ORDER.filter((g) => g in distribution).map((g) => (
                        <li key={g}>
                            {g}: {Math.round(distribution[g] * 100)}%
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    )
}

function Results({ data }: { data: AnalyzeResponse }) {
    return (
        <section aria-label="Analysis results" className="mt-8 space-y-6">
            <div>
                <h2 className="text-lg font-semibold">Grading — case {data.caseId}</h2>
                <div className="mt-3">
                    <GradingPanel grading={data.grading} />
                </div>
            </div>

            <p className="text-sm text-neutral-600">
                Cellular analysis: {data.cellular.status === "not_implemented" ? "not implemented yet" : data.cellular.status}.
                Disease and recommendation analyses are not shown in this version.
            </p>
        </section>
    )
}

export default function AnalysisPage() {
    const analysis = useAnalysis()
    const [caseId, setCaseId] = useState("")
    const [imageUrl, setImageUrl] = useState("")
    const [ecdInput, setEcdInput] = useState("")
    const [ecdError, setEcdError] = useState<string | null>(null)

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        const { ecd, error } = parseEcd(ecdInput)
        setEcdError(error)
        if (error) return
        analysis.mutate({ caseId: caseId.trim(), imageUrl: imageUrl.trim(), ecd })
    }

    return (
        <main className="mx-auto max-w-2xl p-8">
            <h1 className="text-2xl font-bold">Donor cornea grading</h1>

            <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-4">
                <label className="block">
                    <span className="text-sm font-medium">Case ID</span>
                    <input
                        className="mt-1 w-full rounded-md border px-3 py-2"
                        value={caseId}
                        onChange={(e) => setCaseId(e.target.value)}
                        required
                    />
                </label>

                <label className="block">
                    <span className="text-sm font-medium">Specular microscopy image URL</span>
                    <input
                        className="mt-1 w-full rounded-md border px-3 py-2"
                        type="url"
                        value={imageUrl}
                        onChange={(e) => setImageUrl(e.target.value)}
                        required
                    />
                </label>

                <div>
                    <label htmlFor="ecd" className="text-sm font-medium">
                        ECD (cells/mm²)
                    </label>
                    <input
                        id="ecd"
                        className="mt-1 w-full rounded-md border px-3 py-2"
                        inputMode="decimal"
                        value={ecdInput}
                        onChange={(e) => setEcdInput(e.target.value)}
                        aria-invalid={ecdError !== null}
                        aria-describedby={ecdError ? "ecd-help ecd-error" : "ecd-help"}
                    />
                    <p id="ecd-help" className="mt-1 text-xs text-neutral-600">
                        From the specular microscopy report. Leave blank if unavailable; the case will be
                        marked for manual grading.
                    </p>
                    {ecdError && (
                        <p id="ecd-error" role="alert" className="mt-1 text-sm text-red-600">
                            {ecdError}
                        </p>
                    )}
                </div>

                <button
                    type="submit"
                    className="rounded-md border px-4 py-2 font-medium disabled:opacity-50"
                    disabled={analysis.isPending || caseId.trim() === "" || imageUrl.trim() === ""}
                >
                    {analysis.isPending ? "Analyzing…" : "Grade tissue"}
                </button>
            </form>

            {analysis.isError && (
                <p role="alert" className="mt-6 text-red-600">
                    {analysis.error.message}
                </p>
            )}

            {analysis.isSuccess && <Results data={analysis.data} />}
        </main>
    )
}
