import { createBrowserRouter, type RouteObject } from "react-router-dom"
import { HomeRedirect } from "@/components/auth/HomeRedirect"
import { ProtectedRoute } from "@/components/auth/ProtectedRoute"
import { RoleGuard } from "@/components/auth/RoleGuard"
import { AppLayout } from "@/components/layout/AppLayout"
import { PLANNED_MODULES } from "@/lib/roles"
import { ComingSoonPage } from "@/pages/ComingSoonPage"
import { LoginPage } from "@/pages/LoginPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { UnauthorizedPage } from "@/pages/UnauthorizedPage"
import { AdminDashboard } from "@/pages/dashboards/AdminDashboard"
import { ManagerDashboard } from "@/pages/dashboards/ManagerDashboard"
import { DoctorDashboard, NurseDashboard } from "@/pages/dashboards/ClinicalDashboard"
import { SupportDashboard } from "@/pages/dashboards/SupportDashboard"

export const routes: RouteObject[] = [
    { path: "/login", element: <LoginPage /> },
    {
        element: <ProtectedRoute />,
        children: [
            { index: true, element: <HomeRedirect /> },
            {
                element: <AppLayout />,
                children: [
                    {
                        element: <RoleGuard allow={["ADMIN"]} />,
                        children: [{ path: "/admin/dashboard", element: <AdminDashboard /> }],
                    },
                    {
                        element: <RoleGuard allow={["MANAGER"]} />,
                        children: [{ path: "/manager/dashboard", element: <ManagerDashboard /> }],
                    },
                    {
                        element: <RoleGuard allow={["DOCTOR"]} />,
                        children: [{ path: "/doctor/dashboard", element: <DoctorDashboard /> }],
                    },
                    {
                        element: <RoleGuard allow={["NURSE"]} />,
                        children: [{ path: "/nurse/dashboard", element: <NurseDashboard /> }],
                    },
                    {
                        element: <RoleGuard allow={["SUPPORT_STAFF"]} />,
                        children: [{ path: "/support/dashboard", element: <SupportDashboard /> }],
                    },
                    ...PLANNED_MODULES.map(
                        (module): RouteObject => ({
                            element: <RoleGuard allow={module.roles} />,
                            children: [
                                {
                                    path: module.to,
                                    element: <ComingSoonPage title={module.label} description={module.description} />,
                                },
                            ],
                        }),
                    ),
                    { path: "/unauthorized", element: <UnauthorizedPage /> },
                ],
            },
        ],
    },
    { path: "*", element: <NotFoundPage /> },
]

const router = createBrowserRouter(routes)

export default router
