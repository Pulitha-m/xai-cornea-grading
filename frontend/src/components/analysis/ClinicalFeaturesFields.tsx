import { useId } from "react"
import { FEATURE_GROUPS, FEATURES, type FeatureDef, type FeatureInputs } from "@/lib/grading-features"
import { textInput } from "@/lib/styles"

const NOT_RECORDED = "Not recorded"

/**
 * The 24 grading inputs, grouped as on the Konan report and slit-lamp record. Blank means
 * "not recorded", which the model handles as in training; it is never read as zero or "No".
 */
export function ClinicalFeaturesFields({
    values,
    errors,
    onChange,
}: {
    values: FeatureInputs
    errors: Record<string, string>
    onChange: (name: string, value: string) => void
}) {
    return (
        <div className="space-y-5">
            {FEATURE_GROUPS.map((group) => (
                <fieldset key={group.id} className="space-y-3">
                    <legend className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {group.title}
                    </legend>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {FEATURES.filter((f) => f.group === group.id).map((feature) => (
                            <FeatureField
                                key={feature.name}
                                feature={feature}
                                value={values[feature.name] ?? ""}
                                error={errors[feature.name] ?? null}
                                onChange={(value) => onChange(feature.name, value)}
                            />
                        ))}
                    </div>
                </fieldset>
            ))}
        </div>
    )
}

function FeatureField({
    feature,
    value,
    error,
    onChange,
}: {
    feature: FeatureDef
    value: string
    error: string | null
    onChange: (value: string) => void
}) {
    const id = useId()
    const errorId = useId()
    const common = {
        id,
        name: feature.name,
        value,
        "aria-invalid": error !== null,
        "aria-describedby": error ? errorId : undefined,
        className: textInput,
    }

    return (
        <div>
            <label htmlFor={id} className="mb-1 block text-xs font-medium">
                {feature.label}
                {feature.unit && <span className="font-normal text-muted-foreground"> ({feature.unit})</span>}
            </label>
            {feature.type === "number" ? (
                <input
                    {...common}
                    inputMode={feature.integer ? "numeric" : "decimal"}
                    placeholder={NOT_RECORDED}
                    onChange={(e) => onChange(e.target.value)}
                />
            ) : (
                <select {...common} onChange={(e) => onChange(e.target.value)}>
                    <option value="">{NOT_RECORDED}</option>
                    {feature.type === "binary" ? (
                        <>
                            <option value="1">Yes</option>
                            <option value="0">No</option>
                        </>
                    ) : (
                        feature.options!.map((option) => (
                            <option key={option} value={option}>
                                {option}
                            </option>
                        ))
                    )}
                </select>
            )}
            {error && (
                <p id={errorId} role="alert" className="mt-1 text-xs text-destructive">
                    {error}
                </p>
            )}
        </div>
    )
}
