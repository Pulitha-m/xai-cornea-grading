import { createBrowserRouter } from "react-router-dom"
import AnalysisPage from "@/pages/analysis-page"

const router = createBrowserRouter([
    {
        path: "/",
        element: <AnalysisPage />,
    },
])

export default router
