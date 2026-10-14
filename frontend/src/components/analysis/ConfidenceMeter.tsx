export function ConfidenceMeter({ value }: { value: number | null }) {
    if (value === null) {
        return <p className="text-xs text-muted-foreground">Confidence not reported</p>
    }

    const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100)

    return (
        <div>
            <div className="flex items-center justify-between text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                <span>Model confidence</span>
                <span className="text-foreground tabular-nums">{percent}%</span>
            </div>
            <div
                role="meter"
                aria-label="Model confidence"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
                className="mt-1.5 h-1.5 w-full rounded-full bg-muted"
            >
                <div className="h-1.5 rounded-full bg-ring" style={{ width: `${percent}%` }} />
            </div>
        </div>
    )
}
