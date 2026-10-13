import { useQuery } from "@tanstack/react-query"
import { listUsers, USERS_QUERY_KEY } from "@/api/users"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { ROLES } from "@/types/auth"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { UserDirectory } from "@/components/dashboard/UserDirectory"

export function ManagerDashboard() {
    const { user } = useAuth()
    const users = useQuery({ queryKey: USERS_QUERY_KEY, queryFn: listUsers })

    return (
        <>
            <PageHeader title="Operations" description={`Signed in as ${user?.fullName}. Staffing overview across roles.`} />

            <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-5">
                {ROLES.map((role) => (
                    <div key={role} className="rounded-xl border border-border bg-card p-4 shadow-xs">
                        <p className="text-xs text-muted-foreground">{ROLE_LABELS[role]}</p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums">
                            {users.data ? users.data.filter((u) => u.role === role && u.enabled).length : "–"}
                        </p>
                    </div>
                ))}
            </div>

            <Card title="Staff directory" description="Read-only view of active and disabled accounts.">
                <UserDirectory />
            </Card>
        </>
    )
}
