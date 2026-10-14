import { useAuth } from "@/hooks/use-auth"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { CreateUserForm } from "@/components/dashboard/CreateUserForm"
import { UserDirectory } from "@/components/dashboard/UserDirectory"

export function AdminDashboard() {
    const { user } = useAuth()

    return (
        <>
            <PageHeader
                title="Administration"
                description={`Signed in as ${user?.fullName}. Manage staff accounts and role assignments.`}
            />
            <div className="grid gap-6">
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
