import type { ReactNode } from "react"
import { cn } from "cn"

/** A labelled measurement inside a <dl>. Missing values read "Not available" rather than being guessed. */
export function Field({ label, value, unit }: { label: string; value: ReactNode | null | undefined; unit?: string }) {
    const empty = value === null || value === undefined || value === ""

    return (
        <div className="min-w-0">
            <dt className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">{label}</dt>
            <dd className={cn("mt-1", empty ? "text-sm text-muted-foreground" : "text-lg font-semibold tabular-nums")}>
                {empty ? "Not available" : value}
                {!empty && unit && <span className="ml-1 text-xs font-normal text-muted-foreground">{unit}</span>}
            </dd>
        </div>
    )
}
