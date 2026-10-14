import type { ReactNode } from "react"

/** Centered message used by the 403 / 404 pages. */
export function StatusPage({
    icon,
    code,
    title,
    description,
    action,
}: {
    icon?: ReactNode
    code: string
    title: string
    description: string
    action: ReactNode
}) {
    return (
        <section className="mx-auto flex max-w-md flex-col items-center py-16 text-center" aria-labelledby="status-title">
            {icon && (
                <div className="mb-5 flex size-12 items-center justify-center rounded-full bg-accent-soft text-accent">
                    {icon}
                </div>
            )}
            <p className="text-sm font-medium text-accent">{code}</p>
            <h1 id="status-title" className="mt-1 text-2xl font-semibold tracking-tight">
                {title}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
            <div className="mt-6">{action}</div>
        </section>
    )
}
