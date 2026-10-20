import { useId, useState, type FormEvent } from "react"
import type { FollowupRequest } from "@/api/recommendation"
import { useFollowupRecommendation } from "@/hooks/use-recommendation"
import { ApiError } from "@/lib/api-client"
import { EMPTY_FOLLOWUP, MEASURES, VISITS, toFollowupRequest, type FollowupValues, type VisitKey } from "@/lib/followup-form"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { FollowupResults } from "@/components/recommendation/FollowupResults"

const PROCEDURES = ["PK", "DSEK", "DMEK"] as const
const INDICATIONS = ["Fuchs/Endothelial", "Bullous keratopathy", "Failed/Re-graft", "Other"]

/** Enter a graft's first-year visits; get the predicted trajectory, risk, alert and next visit. */
export function FollowupPanel() {
    const recommendation = useFollowupRecommendation()
    const [values, setValues] = useState<FollowupValues>(EMPTY_FOLLOWUP)
    const [procedure, setProcedure] = useState<FollowupRequest["procedure"]>("PK")
    const [indication, setIndication] = useState(INDICATIONS[0])
    const [rejection, setRejection] = useState(false)
    const [missing, setMissing] = useState<string[]>([])
    const ids = useId()

    const serverError = recommendation.error instanceof ApiError ? recommendation.error : null
    const generalError = recommendation.isError ? (serverError?.message ?? recommendation.error.message) : null
    const result = recommendation.isSuccess ? recommendation.data : null

    function set(key: keyof FollowupValues, value: string) {
        setValues((current) => ({ ...current, [key]: value }))
        recommendation.reset()
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        const { request, missing: gaps } = toFollowupRequest(values, procedure, indication, rejection)
        setMissing(gaps)
        if (request) recommendation.mutate(request)
    }

    const input = (key: keyof FollowupValues, label: string, unit?: string) => (
        <div>
            <label htmlFor={`${ids}-${key}`} className="mb-1.5 block text-sm font-medium">
                {label}
                {unit && <span className="ml-1 text-xs font-normal text-muted-foreground">({unit})</span>}
            </label>
            <input
                id={`${ids}-${key}`}
                inputMode="decimal"
                value={values[key]}
                onChange={(e) => set(key, e.target.value)}
                className={textInput}
            />
        </div>
    )

    return (
        <div className="space-y-6">
            <Card
                title="12-month visit"
                description="Donor values and the specular microscopy at 3, 6 and 12 months after surgery. Leave the 3-month visit empty if it was missed."
            >
                <form className="space-y-5" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-3">
                        {input("graftId", "Graft ID")}
                        <div>
                            <label htmlFor={`${ids}-procedure`} className="mb-1.5 block text-sm font-medium">Procedure</label>
                            <select
                                id={`${ids}-procedure`}
                                value={procedure}
                                onChange={(e) => {
                                    setProcedure(e.target.value as FollowupRequest["procedure"])
                                    recommendation.reset()
                                }}
                                className={textInput}
                            >
                                {PROCEDURES.map((p) => <option key={p}>{p}</option>)}
                            </select>
                        </div>
                        <div>
                            <label htmlFor={`${ids}-indication`} className="mb-1.5 block text-sm font-medium">Indication</label>
                            <select
                                id={`${ids}-indication`}
                                value={indication}
                                onChange={(e) => {
                                    setIndication(e.target.value)
                                    recommendation.reset()
                                }}
                                className={textInput}
                            >
                                {INDICATIONS.map((i) => <option key={i}>{i}</option>)}
                            </select>
                        </div>
                    </div>

                    <fieldset className="grid gap-4 sm:grid-cols-4">
                        <legend className="mb-2 text-2xs font-semibold tracking-wider text-muted-foreground uppercase">Donor</legend>
                        {input("donorAge", "Donor age", "years")}
                        {input("baselineEcd", "Donor ECD", "cells/mm²")}
                        {input("baselineCv", "Donor CV", "%")}
                        {input("baselineHex", "Donor HEX", "%")}
                    </fieldset>

                    {VISITS.map((m) => (
                        <fieldset key={m} className="grid gap-4 sm:grid-cols-3">
                            <legend className="mb-2 text-2xs font-semibold tracking-wider text-muted-foreground uppercase">
                                {m}-month visit{m === 3 ? " (optional)" : ""}
                            </legend>
                            {MEASURES.map((x) => input(`${x.key}${m}` as VisitKey, `${m}-month ${x.label}`, x.unit))}
                        </fieldset>
                    ))}

                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox"
                            checked={rejection}
                            onChange={(e) => {
                                setRejection(e.target.checked)
                                recommendation.reset()
                            }}
                            className="size-4"
                        />
                        Rejection episode in the first 12 months
                    </label>

                    {missing.length > 0 && (
                        <p role="alert" className={alertError}>Missing or not a number: {missing.join(", ")}.</p>
                    )}
                    {generalError && <p role="alert" className={alertError}>{generalError}</p>}

                    <button type="submit" className={primaryButton} disabled={recommendation.isPending}>
                        {recommendation.isPending ? <><Spinner /> Calculating…</> : "Get recommendation"}
                    </button>
                </form>
            </Card>
            {result && <FollowupResults result={result} />}
        </div>
    )
}
