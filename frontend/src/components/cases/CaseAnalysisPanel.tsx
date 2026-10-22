import { useId, useState, type FormEvent, type ReactNode } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { analyzeCase, CASE_MODULES, MODULE_LABELS, type CaseImage, type CaseModule, type DonorCase, type ModuleOutcome } from "@/api/cases"
import { CellularResults } from "@/components/cellular/CellularResults"
import { Card } from "@/components/dashboard/PageHeader"
import { CaseDiseaseResults } from "@/components/cases/CaseImages"
import { GradingResults } from "@/components/grading/GradingResults"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"
import { alertError, alertWarning, primaryButton, textInput } from "@/lib/styles"

const NEEDS_DETAILS: CaseModule[] = ["grading", "disease"]

/**
 * Runs the chosen modules on one of the case's images with the saved case details. Each module's
 * result is kept with the case; one module failing never hides another's result. Cellular results
 * are shown alongside and feed no other module.
 */
export function CaseAnalysisPanel({ donorCase, images }: { donorCase: DonorCase; images: CaseImage[] }) {
    const queryClient = useQueryClient()
    const [imageId, setImageId] = useState(images[0]?.id ?? "")
    const [modules, setModules] = useState<CaseModule[]>([...CASE_MODULES])
    const [forceDisease, setForceDisease] = useState(false)
    const imageSelectId = useId()

    const run = useMutation({
        mutationFn: (selected: string) => analyzeCase(donorCase.id, { imageId: selected, modules, forceDisease }),
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["case", donorCase.id, "runs"] }),
    })

    if (images.length === 0) {
        return (
            <Card title="Analyse">
                <EmptyState title="No image to analyse" description="Add a specular microscopy image in the Images tab first." />
            </Card>
        )
    }

    const missingDetails = donorCase.details.ecd === null && modules.some((m) => NEEDS_DETAILS.includes(m))
    const selectedImage = images.some((i) => i.id === imageId) ? imageId : images[0].id

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        if (modules.length === 0) return
        run.mutate(selectedImage)
    }

    const result = run.data

    return (
        <div className="space-y-6">
            <Card title="Analyse" description="Runs on one image with the saved case details. Results are kept in the case history.">
                <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                    <div className="sm:w-80">
                        <label htmlFor={imageSelectId} className="mb-1.5 block text-sm font-medium">Image</label>
                        <select id={imageSelectId} value={selectedImage} onChange={(e) => { setImageId(e.target.value); run.reset() }}
                            className={textInput}>
                            {images.map((image, index) => (
                                <option key={image.id} value={image.id}>
                                    Image {images.length - index} ({new Date(image.uploadedAt).toLocaleString("en-GB")})
                                </option>
                            ))}
                        </select>
                    </div>

                    <fieldset>
                        <legend className="mb-1.5 text-sm font-medium">Modules</legend>
                        <div className="flex flex-wrap gap-4">
                            {CASE_MODULES.map((module) => (
                                <label key={module} className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        checked={modules.includes(module)}
                                        onChange={(e) => {
                                            setModules((current) => e.target.checked
                                                ? CASE_MODULES.filter((m) => m === module || current.includes(m))
                                                : current.filter((m) => m !== module))
                                            run.reset()
                                        }}
                                    />
                                    {MODULE_LABELS[module]}
                                </label>
                            ))}
                        </div>
                    </fieldset>

                    {modules.includes("disease") && (
                        <label className="flex items-center gap-2 text-sm">
                            <input type="checkbox" checked={forceDisease} onChange={(e) => setForceDisease(e.target.checked)} />
                            Run disease screening even if its input checks fail (the result is marked not reliable)
                        </label>
                    )}

                    {missingDetails && (
                        <p className={alertWarning}>
                            Grading and disease screening need the Konan measurements (at least ECD). Enter them in the Details tab.
                        </p>
                    )}

                    <button type="submit" disabled={run.isPending || modules.length === 0} className={primaryButton}>
                        {run.isPending && <Spinner />}
                        {run.isPending ? "Analysing…" : "Run analysis"}
                    </button>
                </form>
                {run.isError && <p role="alert" className={`mt-4 ${alertError}`}>{run.error.message}</p>}
            </Card>

            {result && (
                <>
                    {result.consistency.length > 0 && (
                        <div role="status" className={`${alertWarning} space-y-1`}>
                            <p className="font-semibold">For review: the modules disagree</p>
                            <ul className="list-disc pl-5">
                                {result.consistency.map((flag) => <li key={flag.code}>{flag.message}</li>)}
                            </ul>
                        </div>
                    )}
                    {result.modules.cellular && (
                        <ModuleResult label={MODULE_LABELS.cellular} outcome={result.modules.cellular}
                            render={(r) => <CellularResults result={r} />} />
                    )}
                    {result.modules.grading && (
                        <ModuleResult label={MODULE_LABELS.grading} outcome={result.modules.grading}
                            render={(r) => <GradingResults result={r} />} />
                    )}
                    {result.modules.disease && (
                        <ModuleResult label={MODULE_LABELS.disease} outcome={result.modules.disease}
                            render={(r) => <CaseDiseaseResults caseId={donorCase.id} imageId={selectedImage} result={r} />} />
                    )}
                </>
            )}
        </div>
    )
}

function ModuleResult<T>({ label, outcome, render }: { label: string; outcome: ModuleOutcome<T>; render: (result: T) => ReactNode }) {
    if (outcome.status === "completed" && outcome.result) return <>{render(outcome.result)}</>
    return (
        <Card title={label} actions={<StatusBadge tone="danger">{outcome.status === "rejected" ? "Not run" : "Failed"}</StatusBadge>}>
            <p role="alert" className={alertError}>{outcome.message ?? "The analysis could not be completed."}</p>
        </Card>
    )
}
