import { BrainCircuitIcon } from "lucide-react"
import { AnalysisPanel } from "@/components/dashboard/AnalysisPanel"
import { PageHeader } from "@/components/dashboard/PageHeader"

export function AnalysisPage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <BrainCircuitIcon aria-hidden="true" />
                        AI intelligence
                    </>
                }
                title="Analysis workspace"
                description="Run the cellular, grading, disease and recommendation modules on a specular microscopy image. Each module reports independently."
            />
            <AnalysisPanel />
        </>
    )
}
