import type { ReactNode } from "react"

/** Centered message card used by the 403 / 404 pages. */
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
        <section
            className="mx-auto flex w-full max-w-md flex-col items-center rounded-3xl border border-border bg-card px-6 py-12 text-center shadow-bento sm:px-10"
            aria-labelledby="status-title"
        >
            {icon && (
                <div className="mb-5 flex size-12 items-center justify-center rounded-2xl border border-secondary bg-accent-soft text-accent [&_svg]:size-6">
                    {icon}
                </div>
            )}
            <p className="text-2xs font-bold tracking-wider text-accent uppercase">Error {code}</p>
            <h1 id="status-title" className="mt-1 text-xl font-bold tracking-tight">
                {title}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
            <div className="mt-6">{action}</div>
        </section>
    )
}
