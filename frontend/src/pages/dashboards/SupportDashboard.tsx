import { useQuery } from "@tanstack/react-query"
import { LifeBuoyIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { StatusBadge } from "@/components/ui/status-badge"

async function fetchHealth(): Promise<{ status: string }> {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ""}/actuator/health`)
    if (!response.ok) {
        return { status: "DOWN" }
    }
    return response.json()
}

export function SupportDashboard() {
    const { user } = useAuth()
    const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000 })
    const status = health.data?.status ?? (health.isError ? "UNREACHABLE" : "…")
    const tone = status === "UP" ? "success" : health.isPending ? "neutral" : "danger"

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <LifeBuoyIcon aria-hidden="true" />
                        Support portal
                    </>
                }
                title="Support"
                description={`Signed in as ${user?.fullName}. Operational support tools.`}
            />

            <div className="grid gap-6 sm:grid-cols-2">
                <Card title="Platform status" description="Backend API health, refreshed every 30 seconds.">
                    <p className="flex items-center justify-between gap-3 text-sm">
                        Backend API
                        <StatusBadge tone={tone}>{status}</StatusBadge>
                    </p>
                </Card>

                <Card title="Your access">
                    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                        <dt className="text-muted-foreground">Role</dt>
                        <dd>{user && ROLE_LABELS[user.role]}</dd>
                        <dt className="text-muted-foreground">Username</dt>
                        <dd>{user?.username}</dd>
                    </dl>
                    <p className="mt-3 text-xs text-muted-foreground">
                        Clinical records and administrative tools are not available to this role.
                    </p>
                </Card>
            </div>
        </>
    )
}
