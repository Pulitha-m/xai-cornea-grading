import type { GradingExplanation } from "@/api/grading"
import { featureLabel, formatFeatureValue } from "@/lib/grading-features"
import { Card } from "@/components/dashboard/PageHeader"

/** Rows shown individually; the rest are summed into one "other inputs" row. */
const SHOWN_ROWS = 8

/**
 * Effect sizes on the share of trees voting for the grade (0–1), in words for end users:
 * below LITTLE is "Little effect", from STRONG up is "strongly", in between "slightly".
 */
const LITTLE = 0.02
const STRONG = 0.1

/** Below this share of the image's effect on the maps, say that part of it could not be placed. */
const MOSTLY_MAPPED = 0.5

interface Row {
    key: string
    label: string
    detail: string | null
    contribution: number
}

/** A SHAP contribution in words, e.g. "Raised strongly", without numbers. */
function effectLabel(value: number): { text: string; minor: boolean } {
    if (Math.abs(value) < LITTLE) {
        return { text: "Little effect", minor: true }
    }
    return { text: `${value > 0 ? "Raised" : "Lowered"} ${Math.abs(value) >= STRONG ? "strongly" : "slightly"}`, minor: false }
}

function rowsOf(explanation: GradingExplanation): Row[] {
    const all: Row[] = [
        ...explanation.features.map((f) => ({
            key: f.name,
            label: featureLabel(f.name),
            detail: formatFeatureValue(f.name, f.value) ?? "Not recorded",
            contribution: f.contribution,
        })),
        { key: "image", label: "Specular image", detail: null, contribution: explanation.imageContribution },
    ].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))

    const shown = all.slice(0, SHOWN_ROWS)
    const rest = all.slice(SHOWN_ROWS)
    if (rest.length > 0) {
        shown.push({
            key: "other",
            label: `${rest.length} other inputs`,
            detail: "together",
            contribution: rest.reduce((sum, r) => sum + r.contribution, 0),
        })
    }
    return shown
}

/** What raised or lowered the model's support for the grade (SHAP), and where in the image (SHAP-weighted map). */
export function GradingExplanationView({ explanation }: { explanation: GradingExplanation }) {
    const grade = explanation.explainedGrade
    const rows = rowsOf(explanation)
    const scale = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9)
    const map = explanation.imageMap

    return (
        <div className="grid gap-6 lg:grid-cols-2">
            <Card
                title="What drove this grade"
                description={`How each input moved the model towards grade ${grade} or away from it, compared with a typical training tissue.`}
            >
                <div className="space-y-4">
                    <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Legend">
                        <li className="flex items-center gap-1.5">
                            <span className="size-2.5 rounded-sm bg-attr-raise" aria-hidden="true" />
                            Raised support for {grade}
                        </li>
                        <li className="flex items-center gap-1.5">
                            <span className="size-2.5 rounded-sm bg-attr-lower" aria-hidden="true" />
                            Lowered support for {grade}
                        </li>
                    </ul>

                    <ul className="space-y-2.5" aria-label={`Effects on grade ${grade}`}>
                        {rows.map((row) => (
                            <ContributionRow key={row.key} row={row} scale={scale} grade={grade} />
                        ))}
                    </ul>

                    <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted-foreground">
                        <li>Longer bars mattered more. &ldquo;Little effect&rdquo; means the input barely changed the result.</li>
                        <li>Inputs that were not recorded were handled as in training, never as &ldquo;No&rdquo; or zero.</li>
                        <li>This shows what the model relied on, not what causes the tissue&rsquo;s condition. A specialist must confirm the grade.</li>
                    </ul>
                </div>
            </Card>

            <Card title="Where in the image" description={`The parts of the specular image that moved the model towards grade ${grade} or away from it.`}>
                {map ? (
                    <div className="space-y-4">
                        <div className="grid gap-4 sm:grid-cols-2">
                            <MapFigure png={map.supportingPng} title={`Raised support for ${grade}`} total={map.supportingTotal} />
                            <MapFigure png={map.opposingPng} title={`Lowered support for ${grade}`} total={map.opposingTotal} />
                        </div>
                        <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted-foreground">
                            <li>Brighter areas mattered more. Each map is scaled on its own, so compare the labels under them, not their colours.</li>
                            <li>Check the highlighted areas yourself: the map shows where the model looked, not the outline of a defect.</li>
                            <li>If the brightest area is on the image border, a reflection or an out-of-focus patch, treat the grade with extra caution.</li>
                            {map.localisedShare < MOSTLY_MAPPED && (
                                <li>Part of the image&rsquo;s effect could not be placed on the maps.</li>
                            )}
                        </ul>
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        No image map is available for this grade. The image&rsquo;s overall effect is shown in &ldquo;What drove this grade&rdquo;.
                    </p>
                )}
            </Card>
        </div>
    )
}

function ContributionRow({ row, scale, grade }: { row: Row; scale: number; grade: string }) {
    const width = (Math.abs(row.contribution) / scale) * 50
    const raises = row.contribution >= 0
    const effect = effectLabel(row.contribution)
    const summary = `${row.label}${row.detail ? ` (${row.detail})` : ""}: ${effect.text.toLowerCase()} for ${grade}`

    return (
        <li className="grid grid-cols-[minmax(0,11rem)_1fr_7.5rem] items-center gap-3 text-xs" title={summary} aria-label={summary}>
            <span className="min-w-0">
                <span className="block truncate font-medium">{row.label}</span>
                {row.detail && <span className="block truncate text-2xs text-muted-foreground">{row.detail}</span>}
            </span>
            <span className="relative h-3" aria-hidden="true">
                <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                <span
                    className={raises
                        ? "absolute inset-y-0.5 left-1/2 rounded-r bg-attr-raise"
                        : "absolute inset-y-0.5 right-1/2 rounded-l bg-attr-lower"}
                    style={{ width: `${width}%` }}
                />
            </span>
            <span className={effect.minor ? "text-right text-muted-foreground" : "text-right font-medium"}>{effect.text}</span>
        </li>
    )
}

function MapFigure({ png, title, total }: { png: string | null; title: string; total: number }) {
    const effect = effectLabel(total)
    return (
        <figure className="space-y-1.5">
            {png ? (
                <img src={`data:image/png;base64,${png}`} alt={`Image areas that ${title.toLowerCase()}`} className="w-full rounded-2xl border border-border" />
            ) : (
                <div className="flex aspect-[4/3] items-center justify-center rounded-2xl border border-border bg-sunken text-xs text-muted-foreground">
                    No area
                </div>
            )}
            <figcaption className="text-xs text-muted-foreground">
                {title}: <span className={effect.minor ? "" : "font-medium text-foreground"}>{effect.text}</span>
            </figcaption>
        </figure>
    )
}
