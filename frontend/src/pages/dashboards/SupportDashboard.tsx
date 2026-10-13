import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"

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

    return (
        <>
            <PageHeader title="Support" description={`Signed in as ${user?.fullName}. Operational support tools.`} />

            <div className="grid gap-6 sm:grid-cols-2">
                <Card title="Platform status" description="Backend API health, refreshed every 30 seconds.">
                    <p className="flex items-center gap-2 text-sm">
                        <span
                            className={status === "UP" ? "size-2 rounded-full bg-accent" : "size-2 rounded-full bg-destructive"}
                            aria-hidden="true"
                        />
                        API: <span className="font-medium">{status}</span>
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
