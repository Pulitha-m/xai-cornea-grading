import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ShieldCheckIcon } from "lucide-react"
import { listUsers, USERS_QUERY_KEY } from "@/api/users"
import { useAuth } from "@/hooks/use-auth"
import type { ManagedUser } from "@/types/auth"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { CreateUserForm } from "@/components/dashboard/CreateUserForm"
import { StatStrip, type Stat } from "@/components/dashboard/StatStrip"
import { UserDirectory } from "@/components/dashboard/UserDirectory"

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

function accountStats(users: ManagedUser[] | undefined, now: number): Stat[] {
    const count = (predicate: (u: ManagedUser) => boolean) => (users ? users.filter(predicate).length : "–")
    const disabled = count((u) => !u.enabled)

    return [
        { label: "Staff accounts", value: users ? users.length : "–", note: "Across all roles" },
        { label: "Active", value: count((u) => u.enabled), note: "Able to sign in" },
        { label: "Disabled", value: disabled, note: "Access revoked", highlight: typeof disabled === "number" && disabled > 0 },
        {
            label: "Signed in this week",
            value: count((u) => u.lastLoginAt !== null && now - Date.parse(u.lastLoginAt) <= WEEK_MS),
            note: "Last 7 days",
        },
    ]
}

export function AdminDashboard() {
    const { user } = useAuth()
    // Shares the cache entry with UserDirectory, so this does not add a request.
    const users = useQuery({ queryKey: USERS_QUERY_KEY, queryFn: listUsers })
    const [now] = useState(() => Date.now())

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <ShieldCheckIcon aria-hidden="true" />
                        Administrator portal
                    </>
                }
                title="Administration"
                description={`Signed in as ${user?.fullName}. Manage staff accounts and role assignments.`}
            />
            <div className="grid gap-6">
                <StatStrip stats={accountStats(users.data, now)} />
                <Card title="Staff accounts" description="Change roles or disable access. Changes take effect immediately.">
                    <UserDirectory />
                </Card>
                <Card title="Create account" description="New staff receive a temporary password from you.">
                    <CreateUserForm />
                </Card>
            </div>
        </>
    )
}
