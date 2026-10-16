import { useId, useState, type FormEvent } from "react"
import { useAnalysis } from "@/hooks/use-analysis"
import { parseEcd } from "@/lib/ecd"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { AnalysisResults } from "@/components/analysis/AnalysisResults"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"

/** Submits a corneal image to the analysis pipeline (requires the analysis:run permission). */
export function AnalysisPanel() {
    const analysis = useAnalysis()
    const [imageUrl, setImageUrl] = useState("")
    const [caseId, setCaseId] = useState("")
    const [ecdInput, setEcdInput] = useState("")
    const [ecdError, setEcdError] = useState<string | null>(null)
    const imageId = useId()
    const caseIdId = useId()
    const ecdId = useId()
    const ecdHelpId = useId()
    const ecdErrorId = useId()

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!imageUrl.trim() || !caseId.trim()) {
            return
        }
        const { ecd, error } = parseEcd(ecdInput)
        setEcdError(error)
        if (error) {
            return
        }
        analysis.mutate({ imageUrl: imageUrl.trim(), caseId: caseId.trim(), ecd })
    }

    return (
        <div className="space-y-6">
            <Card title="Run corneal analysis" description="Submit a specular microscopy image for AI-assisted assessment.">
                <form className="grid gap-4 sm:grid-cols-[1fr_12rem_10rem_auto] sm:items-end" onSubmit={handleSubmit}>
                    <div>
                        <label htmlFor={imageId} className="mb-1.5 block text-sm font-medium">
                            Image URL
                        </label>
                        <input
                            id={imageId}
                            type="url"
                            required
                            value={imageUrl}
                            onChange={(e) => setImageUrl(e.target.value)}
                            className={textInput}
                            placeholder="https://…"
                        />
                    </div>
                    <div>
                        <label htmlFor={caseIdId} className="mb-1.5 block text-sm font-medium">
                            Case ID
                        </label>
                        <input
                            id={caseIdId}
                            required
                            value={caseId}
                            onChange={(e) => setCaseId(e.target.value)}
                            className={textInput}
                            placeholder="CASE-001"
                        />
                    </div>
                    <div>
                        <label htmlFor={ecdId} className="mb-1.5 block text-sm font-medium">
                            ECD (cells/mm²)
                        </label>
                        <input
                            id={ecdId}
                            inputMode="decimal"
                            value={ecdInput}
                            onChange={(e) => setEcdInput(e.target.value)}
                            aria-invalid={ecdError !== null}
                            aria-describedby={ecdError ? `${ecdHelpId} ${ecdErrorId}` : ecdHelpId}
                            className={textInput}
                            placeholder="Optional"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={analysis.isPending}
                        className={primaryButton}
                    >
                        {analysis.isPending && <Spinner />}
                        {analysis.isPending ? "Analysing…" : "Analyse"}
                    </button>
                </form>

                <p id={ecdHelpId} className="mt-3 text-xs text-muted-foreground">
                    Enter ECD from the specular microscopy report to receive an ECD-based grade. Leave it blank if
                    unavailable; the case will be marked for manual grading.
                </p>

                {ecdError && (
                    <p id={ecdErrorId} role="alert" className={`mt-4 ${alertError}`}>
                        {ecdError}
                    </p>
                )}

                {analysis.isError && (
                    <p role="alert" className={`mt-4 ${alertError}`}>
                        {analysis.error.message}
                    </p>
                )}
            </Card>

            {analysis.isSuccess && <AnalysisResults result={analysis.data} />}
        </div>
    )
}
