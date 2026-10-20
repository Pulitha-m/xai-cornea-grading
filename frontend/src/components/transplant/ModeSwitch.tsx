import { cn } from "cn"

/** Two-way switch between working from donor cases and entering values by hand. */
export function ModeSwitch<T extends string>({ label, value, options, onChange }: {
    label: string
    value: T
    options: { value: T; label: string }[]
    onChange: (value: T) => void
}) {
    return (
        <div role="radiogroup" aria-label={label} className="mb-6 flex flex-wrap gap-2">
            {options.map((o) => (
                <button
                    key={o.value}
                    type="button"
                    role="radio"
                    aria-checked={value === o.value}
                    onClick={() => onChange(o.value)}
                    className={cn(
                        "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors",
                        value === o.value ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card hover:bg-sunken",
                    )}
                >
                    {o.label}
                </button>
            ))}
        </div>
    )
}
