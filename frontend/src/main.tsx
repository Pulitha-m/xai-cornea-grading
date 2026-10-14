import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AuthProvider } from "@/components/auth/AuthProvider"
import { ApiError } from "@/lib/api-client"
import router from "./routes"

import "./index.css"

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            // Auth/permission failures will not succeed on retry.
            retry: (failureCount, error) =>
                !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && failureCount < 2,
        },
    },
})

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <QueryClientProvider client={queryClient}>
            <AuthProvider>
                <RouterProvider router={router} />
            </AuthProvider>
        </QueryClientProvider>
    </StrictMode>,
)
