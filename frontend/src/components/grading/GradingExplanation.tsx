import type { GradingExplanation } from "@/api/grading"
import { featureLabel, formatFeatureValue } from "@/lib/grading-features"
import { Card } from "@/components/dashboard/PageHeader"

/** Rows shown individually; the rest are summed into one "other inputs" row. */
const SHOWN_ROWS = 8

interface Row {
    key: string
    label: string
    detail: string | null
    contribution: number
}

/** Share of tree votes as percentage points, e.g. "+9.2 pts". */
function points(value: number) {
    const rounded = Math.round(value * 1000) / 10
    return `${rounded > 0 ? "+" : rounded < 0 ? "−" : "±"}${Math.abs(rounded).toFixed(1)} pts`
}

function percent(value: number) {
    return `${Math.round(value * 100)}%`
}

function rowsOf(explanation: GradingExplanation): Row[] {
    const all: Row[] = [
        ...explanation.features.map((f) => ({
            key: f.name,
            label: featureLabel(f.name),
            detail: formatFeatureValue(f.name, f.value) ?? "Not recorded",
            contribution: f.contribution,
        })),
        { key: "image", label: "Image features", detail: "ResNet-50, 32 components", contribution: explanation.imageContribution },
    ].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))

    const shown = all.slice(0, SHOWN_ROWS)
    const rest = all.slice(SHOWN_ROWS)
    if (rest.length > 0) {
        shown.push({
            key: "other",
            label: `${rest.length} other inputs`,
            detail: "combined",
            contribution: rest.reduce((sum, r) => sum + r.contribution, 0),
        })
    }
    return shown
}

/** SHAP explanation of the grade: what raised or lowered the share of trees voting for it, and where in the image. */
export function GradingExplanationView({ explanation }: { explanation: GradingExplanation }) {
    const grade = explanation.explainedGrade
    const rows = rowsOf(explanation)
    const scale = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9)
    const map = explanation.imageMap

    return (
        <div className="grid gap-6 lg:grid-cols-2">
            <Card
                title="What drove this grade"
                description={`SHAP contributions to the share of trees voting ${grade}: from the training average (${percent(explanation.baseline)}) to this tissue (${percent(explanation.prediction)}).`}
            >
                <div className="space-y-4">
                    <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Legend">
                        <li className="flex items-center gap-1.5">
                            <span className="size-2.5 rounded-sm bg-attr-raise" aria-hidden="true" />
                            Raised the share for {grade}
                        </li>
                        <li className="flex items-center gap-1.5">
                            <span className="size-2.5 rounded-sm bg-attr-lower" aria-hidden="true" />
                            Lowered it
                        </li>
                    </ul>

                    <ul className="space-y-2.5" aria-label={`Contributions to grade ${grade}`}>
                        {rows.map((row) => (
                            <ContributionRow key={row.key} row={row} scale={scale} grade={grade} />
                        ))}
                    </ul>

                    <p className="text-xs text-muted-foreground">{explanation.message}</p>
                </div>
            </Card>

            <Card
                title="Where in the image"
                description="The image's SHAP contribution spread over the image through the backbone's last convolutional layer. A Grad-CAM-style map, but weighted by SHAP: the forest has no gradients."
            >
                {map ? (
                    <div className="space-y-4">
                        <div className="grid gap-4 sm:grid-cols-2">
                            <MapFigure png={map.supportingPng} title={`Raised the share for ${grade}`} total={map.supportingTotal} />
                            <MapFigure png={map.opposingPng} title="Lowered it" total={map.opposingTotal} />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Each map is scaled to its own maximum, so compare their totals, not their colours. The maps
                            cover {percent(map.localisedShare)} of the image&rsquo;s attribution. They show what the model
                            relied on, which may not be clinically meaningful (e.g. image borders); their faithfulness has
                            not been evaluated.
                        </p>
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        No image map: the image backbone in use does not provide feature maps. The image&rsquo;s overall
                        contribution is shown in the chart.
                    </p>
                )}
            </Card>
        </div>
    )
}

function ContributionRow({ row, scale, grade }: { row: Row; scale: number; grade: string }) {
    const width = (Math.abs(row.contribution) / scale) * 50
    const raises = row.contribution >= 0
    const summary = `${row.label}${row.detail ? ` (${row.detail})` : ""}: ${points(row.contribution)} for ${grade}`

    return (
        <li className="grid grid-cols-[minmax(0,11rem)_1fr_4.5rem] items-center gap-3 text-xs" title={summary} aria-label={summary}>
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
            <span className="text-right tabular-nums text-muted-foreground">{points(row.contribution)}</span>
        </li>
    )
}

function MapFigure({ png, title, total }: { png: string | null; title: string; total: number }) {
    return (
        <figure className="space-y-1.5">
            {png ? (
                <img src={`data:image/png;base64,${png}`} alt={`Image regions that ${title.toLowerCase()}`} className="w-full rounded-2xl border border-border" />
            ) : (
                <div className="flex aspect-[4/3] items-center justify-center rounded-2xl border border-border bg-sunken text-xs text-muted-foreground">
                    No region
                </div>
            )}
            <figcaption className="text-xs text-muted-foreground">
                {title} <span className="tabular-nums">({points(total)})</span>
            </figcaption>
        </figure>
    )
}
