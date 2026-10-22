import { TriangleAlertIcon } from "lucide-react"

/** Possible but unusual input values returned with a result: the result stands, the values should be checked. */
export function DataWarnings({ warnings }: { warnings?: string[] }) {
    if (!warnings?.length) return null
    return (
        <section aria-label="Check these values" className="rounded-3xl border border-warning/30 bg-warning-soft px-5 py-4 text-sm sm:px-6">
            <p className="flex items-center gap-2 font-semibold text-warning">
                <TriangleAlertIcon className="size-4" aria-hidden="true" />
                Check these values
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
                {warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
                The result below was still calculated. Correct a value if it was mistyped, then run again.
            </p>
        </section>
    )
}
