import { cn } from "cn"

export interface Stat {
    label: string
    value: number | string
    note?: string
    /** Draws attention to a figure that may need action. */
    highlight?: boolean
}

const COLUMNS: Record<number, string> = {
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-3",
    4: "grid-cols-2 lg:grid-cols-4",
    5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
}

export function StatStrip({ stats }: { stats: Stat[] }) {
    return (
        <dl className={cn("grid gap-4", COLUMNS[stats.length] ?? "sm:grid-cols-3")}>
            {stats.map((stat) => (
                <div
                    key={stat.label}
                    className={cn(
                        "rounded-3xl border p-5 shadow-bento",
                        stat.highlight ? "border-highlight/50 bg-highlight-soft" : "border-border bg-card",
                    )}
                >
                    <dt className={cn("text-xs font-semibold", stat.highlight ? "text-warning" : "text-muted-foreground")}>
                        {stat.label}
                    </dt>
                    <dd className="mt-1 text-2xl leading-none font-bold tabular-nums">{stat.value}</dd>
                    {stat.note && <dd className="mt-1.5 text-2xs text-muted-foreground">{stat.note}</dd>}
                </div>
            ))}
        </dl>
    )
}
