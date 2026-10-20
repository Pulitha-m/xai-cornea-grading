import { useId, useState, type FormEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { updateCaseDetails, type CaseDetails, type DonorCase } from "@/api/cases"
import { ClinicalFeaturesFields } from "@/components/analysis/ClinicalFeaturesFields"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { buildFeaturePayload, FEATURES, type FeatureInputs } from "@/lib/grading-features"
import { alertError, primaryButton, textInput } from "@/lib/styles"

/** Konan fields of CaseDetails by grading feature name. */
const KONAN: [keyof CaseDetails, string][] = [
    ["ecd", "ECD_CD_cells_per_mm2"],
    ["cv", "CV"],
    ["hexPercent", "HEX_percent"],
    ["sd", "SD"],
    ["totalCellCount", "Total_Cell_Count"],
    ["totalAreaUm2", "Total_Area_um2"],
]
const SLIT_LAMP = FEATURES.filter((f) => f.group !== "konan").map((f) => f.name)

interface DonorInputs {
    donorAgeYears: string
    deathToPreservationHours: string
    preservationDate: string
}

function toFeatureInputs(details: CaseDetails): FeatureInputs {
    const inputs: FeatureInputs = {}
    for (const [field, name] of KONAN) {
        const value = details[field]
        inputs[name] = value === null ? "" : String(value)
    }
    for (const name of SLIT_LAMP) {
        const value = details.slitLamp[name]
        inputs[name] = value === null || value === undefined ? "" : String(value)
    }
    return inputs
}

function toDonorInputs(details: CaseDetails): DonorInputs {
    return {
        donorAgeYears: details.donorAgeYears === null ? "" : String(details.donorAgeYears),
        deathToPreservationHours: details.deathToPreservationHours === null ? "" : String(details.deathToPreservationHours),
        preservationDate: details.preservationDate ?? "",
    }
}

function donorErrors(inputs: DonorInputs): Record<string, string> {
    const errors: Record<string, string> = {}
    const age = inputs.donorAgeYears.trim()
    if (age !== "" && !(Number.isInteger(Number(age)) && Number(age) >= 0 && Number(age) <= 120)) {
        errors.donorAgeYears = "Donor age must be a whole number of years from 0 to 120."
    }
    const hours = inputs.deathToPreservationHours.trim()
    if (hours !== "" && !(Number.isFinite(Number(hours)) && Number(hours) >= 0)) {
        errors.deathToPreservationHours = "Death to preservation must be 0 hours or more."
    }
    return errors
}

/**
 * The case details, entered once: donor information, the Konan report and the slit-lamp findings.
 * Grading uses the 24 Konan and slit-lamp values, disease screening the Konan values and donor age.
 */
export function CaseDetailsForm({ donorCase }: { donorCase: DonorCase }) {
    const queryClient = useQueryClient()
    const [features, setFeatures] = useState(() => toFeatureInputs(donorCase.details))
    const [donor, setDonor] = useState(() => toDonorInputs(donorCase.details))
    const [errors, setErrors] = useState<Record<string, string>>({})
    const ageId = useId()
    const hoursId = useId()
    const dateId = useId()

    const save = useMutation({
        mutationFn: (details: CaseDetails) => updateCaseDetails(donorCase.id, details),
        onSuccess: (updated) => {
            queryClient.setQueryData(["case", donorCase.id], updated)
            void queryClient.invalidateQueries({ queryKey: ["cases", "recent"] })
        },
    })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        const { payload, errors: featureErrors } = buildFeaturePayload(features)
        const allErrors = { ...featureErrors, ...donorErrors(donor) }
        setErrors(allErrors)
        if (Object.keys(allErrors).length > 0) return

        const number = (raw: string) => (raw.trim() === "" ? null : Number(raw))
        const konan = (name: string) => payload[name] as number | null
        save.mutate({
            donorAgeYears: number(donor.donorAgeYears),
            deathToPreservationHours: number(donor.deathToPreservationHours),
            preservationDate: donor.preservationDate || null,
            ecd: konan("ECD_CD_cells_per_mm2"),
            cv: konan("CV"),
            hexPercent: konan("HEX_percent"),
            sd: konan("SD"),
            totalCellCount: konan("Total_Cell_Count"),
            totalAreaUm2: konan("Total_Area_um2"),
            slitLamp: Object.fromEntries(SLIT_LAMP.map((name) => [name, payload[name]])),
        })
    }

    function setDonorField(field: keyof DonorInputs, value: string) {
        setDonor((current) => ({ ...current, [field]: value }))
        setErrors((current) => {
            const next = { ...current }
            delete next[field]
            return next
        })
        save.reset()
    }

    const errorCount = Object.keys(errors).length

    return (
        <Card
            title="Case details"
            description="Entered once for the case and used by every analysis. Leave anything not recorded blank; it is never read as zero or “No”."
        >
            <form className="space-y-5" onSubmit={handleSubmit} noValidate>
                <fieldset className="space-y-3">
                    <legend className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">Donor</legend>
                    <div className="grid gap-3 sm:grid-cols-3">
                        <DonorField id={ageId} label="Donor age (years)" value={donor.donorAgeYears} error={errors.donorAgeYears}
                            inputMode="numeric" onChange={(v) => setDonorField("donorAgeYears", v)} />
                        <DonorField id={hoursId} label="Death to preservation (hours)" value={donor.deathToPreservationHours}
                            error={errors.deathToPreservationHours} inputMode="decimal"
                            onChange={(v) => setDonorField("deathToPreservationHours", v)} />
                        <DonorField id={dateId} label="Preservation date" type="date" value={donor.preservationDate}
                            onChange={(v) => setDonorField("preservationDate", v)} />
                    </div>
                </fieldset>

                <ClinicalFeaturesFields
                    values={features}
                    errors={errors}
                    onChange={(name, value) => {
                        setFeatures((current) => ({ ...current, [name]: value }))
                        setErrors((current) => {
                            const next = { ...current }
                            delete next[name]
                            return next
                        })
                        save.reset()
                    }}
                />

                {errorCount > 0 && (
                    <p role="alert" className={alertError}>
                        Correct the {errorCount === 1 ? "highlighted field" : `${errorCount} highlighted fields`} and save again.
                    </p>
                )}
                {save.isError && <p role="alert" className={alertError}>{save.error.message}</p>}

                <div className="flex items-center gap-3">
                    <button type="submit" disabled={save.isPending} className={primaryButton}>
                        {save.isPending && <Spinner />}
                        Save details
                    </button>
                    {save.isSuccess && <p role="status" className="text-sm text-success">Details saved.</p>}
                </div>
            </form>
        </Card>
    )
}

function DonorField({
    id, label, value, error, type = "text", inputMode, onChange,
}: {
    id: string
    label: string
    value: string
    error?: string
    type?: string
    inputMode?: "numeric" | "decimal"
    onChange: (value: string) => void
}) {
    const errorId = `${id}-error`
    return (
        <div>
            <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>
            <input
                id={id}
                type={type}
                inputMode={inputMode}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                aria-invalid={error !== undefined}
                aria-describedby={error ? errorId : undefined}
                className={textInput}
            />
            {error && <p id={errorId} className="mt-1 text-xs text-destructive">{error}</p>}
        </div>
    )
}
