import type { ReactNode } from "react"

export function EmptyState({
    icon,
    title,
    description,
    action,
}: {
    icon?: ReactNode
    title: string
    description?: string
    action?: ReactNode
}) {
    return (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-sunken px-6 py-10 text-center">
            {icon && <div className="mb-2 text-muted-foreground [&_svg]:size-5">{icon}</div>}
            <p className="text-sm font-medium">{title}</p>
            {description && <p className="mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">{description}</p>}
            {action && <div className="mt-3">{action}</div>}
        </div>
    )
}
