import { createBrowserRouter } from "react-router-dom"
import { useAnalysis } from "@/hooks/use-analysis"

function TestPage() {
    const analysis = useAnalysis()

    function handleTest() {
        analysis.mutate({
            imageUrl: "https://example.com/cornea.jpg",
            caseId: "CASE-007",
        })
    }

    return (
        <div className="p-8">
            <h1 className="text-2xl font-bold">Corneal-AI</h1>

            <button
                className="mt-4 rounded-md border px-4 py-2"
                onClick={handleTest}
                disabled={analysis.isPending}
            >
                {analysis.isPending ? "Analyzing..." : "Test Analysis"}
            </button>

            {analysis.isSuccess && (
                <pre className="mt-6 overflow-auto rounded-md border p-4">
          {JSON.stringify(analysis.data, null, 2)}
        </pre>
            )}

            {analysis.isError && (
                <p className="mt-6 text-red-500">
                    {analysis.error.message}
                </p>
            )}
        </div>
    )
}

const router = createBrowserRouter([
    {
        path: "/",
        element: <TestPage />,
    },
])

export default router