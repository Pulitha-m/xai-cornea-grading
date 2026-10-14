import { useId, type ReactNode } from "react"

export function PageHeader({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
    return (
        <div className="mb-6 flex flex-col gap-4 rounded-3xl border border-border bg-card p-6 shadow-bento sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
                <h1 className="text-xl font-bold tracking-tight">{title}</h1>
                <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>
            </div>
            {children && <div className="flex shrink-0 flex-wrap items-center gap-2.5">{children}</div>}
        </div>
    )
}

export function Card({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
    const headingId = useId()

    return (
        <section aria-labelledby={headingId} className="overflow-hidden rounded-3xl border border-border bg-card shadow-bento">
            <header className="border-b border-muted px-5 py-4 sm:px-6">
                <h2 id={headingId} className="text-sm font-semibold">
                    {title}
                </h2>
                {description && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>}
            </header>
            <div className="p-5 sm:p-6">{children}</div>
        </section>
    )
}
