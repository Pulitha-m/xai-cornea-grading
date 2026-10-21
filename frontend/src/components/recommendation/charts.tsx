import type { PredictedEcd } from "@/api/recommendation"

/*
 * Small SVG charts for the recommendation pages (no chart library needed).
 * Colours: one blue for the graft's own series; a validated blue/red diverging pair for
 * "favourable / unfavourable" (CVD-safe on the white card); values are always written as
 * text next to the marks, so colour never carries meaning alone.
 */
const SERIES = "#0369a1"            // app accent: the graft's trajectory
export const FAVOURABLE = "#2a78d6"        // diverging pole: lowers risk / pushes a cornea up
export const UNFAVOURABLE = "#e34948"      // diverging pole: raises risk / pushes a cornea down
const GRID = "#e2e8f0"
const AXIS = "#cbd5e1"
const MUTED = "#64748b"
const INK = "#0f172a"

/* ---------------------------------------------------------------- ECD trajectory */

export function TrajectoryChart({
    observed,
    predicted,
    bandLevel,
}: {
    /** Measured ECD: month 0 = donor, then the visits. */
    observed: { months: number; ecd: number }[]
    predicted: PredictedEcd[]
    bandLevel: string
}) {
    const W = 640, H = 280, L = 52, R = 16, T = 16, B = 40
    const maxY = Math.max(3000, ...observed.map((p) => p.ecd), ...predicted.map((p) => p.high)) * 1.05
    const x = (m: number) => L + (m / 60) * (W - L - R)
    const y = (v: number) => T + (1 - v / maxY) * (H - T - B)
    const last = observed[observed.length - 1]
    const path = (pts: { months: number; ecd: number }[]) =>
        pts.map((p, i) => `${i ? "L" : "M"}${x(p.months).toFixed(1)},${y(p.ecd).toFixed(1)}`).join(" ")
    const band = [
        `M${x(last.months)},${y(last.ecd)}`,
        ...predicted.map((p) => `L${x(p.months)},${y(p.high)}`),
        ...[...predicted].reverse().map((p) => `L${x(p.months)},${y(p.low)}`),
        "Z",
    ].join(" ")
    const yTicks = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500].filter((v) => v <= maxY)
    const xTicks = [0, 3, 6, 12, 24, 36, 48, 60]
    const summary = `Measured ECD ${observed.map((p) => `${p.months} months ${p.ecd}`).join(", ")}; predicted ` +
        predicted.map((p) => `${p.months} months ${p.ecd} (${p.low}–${p.high})`).join(", ")

    return (
        <figure className="space-y-2">
            <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`ECD trajectory. ${summary}`}>
                {yTicks.map((v) => (
                    <g key={v}>
                        <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
                        <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={MUTED}>{v}</text>
                    </g>
                ))}
                {xTicks.map((m) => (
                    <text key={m} x={x(m)} y={H - B + 18} textAnchor="middle" fontSize={11} fill={MUTED}>{m}</text>
                ))}
                <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize={11} fill={MUTED}>Months after surgery</text>
                <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke={AXIS} strokeWidth={1} />

                {[{ v: 1000, label: "Low ECD 1000" }, { v: 500, label: "Failure 500" }].map((r) => (
                    <g key={r.v}>
                        <line x1={L} x2={W - R} y1={y(r.v)} y2={y(r.v)} stroke={MUTED} strokeWidth={1} strokeDasharray="4 4" />
                        <text x={W - R} y={y(r.v) - 5} textAnchor="end" fontSize={11} fill={MUTED}>{r.label}</text>
                    </g>
                ))}

                <path d={band} fill={SERIES} fillOpacity={0.12} stroke="none" />
                <path d={path([last, ...predicted])} fill="none" stroke={SERIES} strokeWidth={2} strokeDasharray="6 4" />
                <path d={path(observed)} fill="none" stroke={SERIES} strokeWidth={2} />

                {observed.map((p) => (
                    <circle key={`o${p.months}`} cx={x(p.months)} cy={y(p.ecd)} r={5} fill={SERIES} stroke="#fff" strokeWidth={2}>
                        <title>{`${p.months === 0 ? "Donor" : `${p.months} months`}: ${p.ecd} cells/mm² (measured)`}</title>
                    </circle>
                ))}
                {predicted.map((p) => (
                    <g key={`p${p.months}`}>
                        <circle cx={x(p.months)} cy={y(p.ecd)} r={5} fill="#fff" stroke={SERIES} strokeWidth={2}>
                            <title>{`${p.months} months: ${p.ecd} cells/mm² predicted (${bandLevel} band ${p.low}–${p.high})`}</title>
                        </circle>
                        <text x={x(p.months)} y={y(p.ecd) - 10} textAnchor="middle" fontSize={11} fontWeight={600} fill={INK}>{p.ecd}</text>
                    </g>
                ))}
            </svg>
            <figcaption className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                    <svg width="22" height="8" aria-hidden="true"><line x1="0" x2="22" y1="4" y2="4" stroke={SERIES} strokeWidth="2" /></svg>
                    Measured
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <svg width="22" height="8" aria-hidden="true"><line x1="0" x2="22" y1="4" y2="4" stroke={SERIES} strokeWidth="2" strokeDasharray="5 3" /></svg>
                    Predicted, shaded {bandLevel} band
                </span>
            </figcaption>
        </figure>
    )
}

/* ---------------------------------------------------------------- reasons */

export interface ReasonBar {
    label: string
    /** Signed size: > 0 means "favourable" when favourablePositive, otherwise "unfavourable". */
    value: number
    /** Text written next to the bar, e.g. "×2.31" or "+0.40". */
    display: string
}

/** Horizontal bars around a centre line: blue = favourable, red = unfavourable, value written beside. */
export function DivergingBars({
    items,
    favourablePositive,
    favourableLabel,
    unfavourableLabel,
    title,
}: {
    items: ReasonBar[]
    favourablePositive: boolean
    favourableLabel: string
    unfavourableLabel: string
    title: string
}) {
    const max = Math.max(...items.map((i) => Math.abs(i.value)), 1e-9)
    return (
        <figure>
            <figcaption className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{title}</span>
                <span className="flex gap-3">
                    <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-sm" style={{ background: UNFAVOURABLE }} aria-hidden="true" />{unfavourableLabel}</span>
                    <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-sm" style={{ background: FAVOURABLE }} aria-hidden="true" />{favourableLabel}</span>
                </span>
            </figcaption>
            <ul className="space-y-1.5">
                {items.map((i) => {
                    const good = favourablePositive ? i.value > 0 : i.value < 0
                    const width = `${(Math.abs(i.value) / max) * 50}%`
                    return (
                        <li key={i.label} className="grid grid-cols-[9.5rem_1fr_4rem] items-center gap-2 text-sm">
                            <span className="truncate text-muted-foreground" title={i.label}>{i.label}</span>
                            <span className="relative h-3 rounded-sm bg-sunken" aria-hidden="true">
                                <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                                <span
                                    className="absolute inset-y-0 rounded-sm"
                                    style={{
                                        width,
                                        background: good ? FAVOURABLE : UNFAVOURABLE,
                                        ...(i.value >= 0 ? { left: "50%" } : { right: "50%" }),
                                    }}
                                />
                            </span>
                            <span className="text-right tabular-nums">
                                {i.display}
                                <span className="sr-only">, {good ? favourableLabel : unfavourableLabel}</span>
                            </span>
                        </li>
                    )
                })}
            </ul>
        </figure>
    )
}

/* ---------------------------------------------------------------- risk against its alert threshold */

export function RiskMeter({ label, probability, threshold, thresholdLabel }: {
    label: string
    probability: number
    threshold: number | null
    thresholdLabel: string
}) {
    const over = threshold !== null && probability >= threshold
    const pct = Math.round(probability * 100)
    return (
        <div>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                <span>{label}</span>
                <span className="font-semibold tabular-nums">
                    {pct}%{threshold !== null && <span className="ml-1 text-xs font-normal text-muted-foreground">({over ? "at or above" : "below"} {Math.round(threshold * 100)}% {thresholdLabel})</span>}
                </span>
            </div>
            <div className="relative h-2.5 rounded-full bg-sunken" role="meter" aria-label={label} aria-valuemin={0}
                aria-valuemax={100} aria-valuenow={pct}>
                <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(pct, 1)}%`, background: over ? UNFAVOURABLE : SERIES }} />
                {threshold !== null && (
                    <div className="absolute -inset-y-1 w-0.5 bg-foreground" style={{ left: `${threshold * 100}%` }} title={`${thresholdLabel} threshold ${Math.round(threshold * 100)}%`} />
                )}
            </div>
        </div>
    )
}

/* ---------------------------------------------------------------- MCDA criterion scores (0-1) */

export function ScoreBars({ scores }: { scores: Record<string, number> }) {
    return (
        <ul className="space-y-1.5">
            {Object.entries(scores).map(([k, v]) => (
                <li key={k} className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-2 text-sm">
                    <span className="truncate text-muted-foreground">{k.replaceAll("_", " ")}</span>
                    <span className="h-2.5 rounded-sm bg-sunken" aria-hidden="true">
                        <span className="block h-full rounded-sm" style={{ width: `${Math.max(v * 100, 1)}%`, background: SERIES }} />
                    </span>
                    <span className="text-right tabular-nums">{v.toFixed(2)}</span>
                </li>
            ))}
        </ul>
    )
}
