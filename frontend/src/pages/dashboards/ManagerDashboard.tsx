import { useQuery } from "@tanstack/react-query"
import { BuildingIcon } from "lucide-react"
import { listUsers, USERS_QUERY_KEY } from "@/api/users"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { ROLES } from "@/types/auth"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { StatStrip } from "@/components/dashboard/StatStrip"
import { UserDirectory } from "@/components/dashboard/UserDirectory"

export function ManagerDashboard() {
    const { user } = useAuth()
    const users = useQuery({ queryKey: USERS_QUERY_KEY, queryFn: listUsers })

    const stats = ROLES.map((role) => ({
        label: ROLE_LABELS[role],
        value: users.data ? users.data.filter((u) => u.role === role && u.enabled).length : "–",
        note: "Active accounts",
    }))

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <BuildingIcon aria-hidden="true" />
                        Manager portal
                    </>
                }
                title="Operations"
                description={`Signed in as ${user?.fullName}. Staffing overview across roles.`}
            />

            <div className="grid gap-6">
                <StatStrip stats={stats} />
                <Card title="Staff directory" description="Read-only view of active and disabled accounts.">
                    <UserDirectory />
                </Card>
            </div>
        </>
    )
}
