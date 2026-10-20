import { createBrowserRouter, type RouteObject } from "react-router-dom"
import { HomeRedirect } from "@/components/auth/HomeRedirect"
import { ProtectedRoute } from "@/components/auth/ProtectedRoute"
import { RoleGuard } from "@/components/auth/RoleGuard"
import { AppLayout } from "@/components/layout/AppLayout"
import { ANALYSIS_PATH, CASES_PATH, CELLULAR_PATH, DISEASE_PATH, GRADING_PATH, PLANNED_MODULES } from "@/lib/roles"
import { AnalysisPage } from "@/pages/AnalysisPage"
import { CaseWorkspacePage } from "@/pages/CaseWorkspacePage"
import { CasesPage } from "@/pages/CasesPage"
import { CellularPage } from "@/pages/CellularPage"
import { ComingSoonPage } from "@/pages/ComingSoonPage"
import { DiseasePage } from "@/pages/DiseasePage"
import { GradingPage } from "@/pages/GradingPage"
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
                    {
                        element: <RoleGuard allow={["DOCTOR", "NURSE"]} permission="analysis:run" />,
                        children: [
                            { path: CASES_PATH, element: <CasesPage /> },
                            { path: `${CASES_PATH}/:caseId`, element: <CaseWorkspacePage /> },
                        ],
                    },
                    {
                        element: <RoleGuard allow={["DOCTOR", "NURSE"]} permission="analysis:run" />,
                        children: [{ path: ANALYSIS_PATH, element: <AnalysisPage /> }],
                    },
                    {
                        element: <RoleGuard allow={["DOCTOR", "NURSE"]} permission="analysis:run" />,
                        children: [{ path: CELLULAR_PATH, element: <CellularPage /> }],
                    },
                    {
                        element: <RoleGuard allow={["DOCTOR", "NURSE"]} permission="analysis:run" />,
                        children: [{ path: GRADING_PATH, element: <GradingPage /> }],
                    },
                    {
                        element: <RoleGuard allow={["DOCTOR", "NURSE"]} permission="analysis:run" />,
                        children: [{ path: DISEASE_PATH, element: <DiseasePage /> }],
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
