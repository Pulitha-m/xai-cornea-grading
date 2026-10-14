import type { ReactNode } from "react"

export function PageHeader({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
    return (
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
                <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
                <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            </div>
            {children}
        </div>
    )
}

export function Card({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
    return (
        <section className="rounded-xl border border-border bg-card p-5 shadow-xs sm:p-6">
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
            <div className="mt-4">{children}</div>
        </section>
    )
}
