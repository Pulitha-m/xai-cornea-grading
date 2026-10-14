import { useId, useState, type FormEvent } from "react"
import { useAnalysis } from "@/hooks/use-analysis"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { AnalysisResults } from "@/components/analysis/AnalysisResults"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"

/** Submits a corneal image to the analysis pipeline (requires the analysis:run permission). */
export function AnalysisPanel() {
    const analysis = useAnalysis()
    const [imageUrl, setImageUrl] = useState("")
    const [caseId, setCaseId] = useState("")
    const imageId = useId()
    const caseIdId = useId()

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!imageUrl.trim() || !caseId.trim()) {
            return
        }
        analysis.mutate({ imageUrl: imageUrl.trim(), caseId: caseId.trim() })
    }

    return (
        <div className="space-y-6">
            <Card title="Run corneal analysis" description="Submit a specular microscopy image for AI-assisted assessment.">
                <form className="grid gap-4 sm:grid-cols-[1fr_12rem_auto] sm:items-end" onSubmit={handleSubmit}>
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
                    <button
                        type="submit"
                        disabled={analysis.isPending}
                        className={primaryButton}
                    >
                        {analysis.isPending && <Spinner />}
                        {analysis.isPending ? "Analysing…" : "Analyse"}
                    </button>
                </form>

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
