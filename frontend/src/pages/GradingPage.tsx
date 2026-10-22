import { GaugeIcon } from "lucide-react"
import { PreviousResults } from "@/components/cases/PreviousResults"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { GradingPanel } from "@/components/grading/GradingPanel"

export function GradingPage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <GaugeIcon aria-hidden="true" />
                        AI intelligence
                    </>
                }
                title="Cornea grading"
                description="Grades donor corneas (A+, A or B) from a specular microscopy image and 24 Konan and slit-lamp inputs with the hybrid model, and shows what drove each grade. Decision support for specialist review — not an eye-bank grading decision."
            />
            <GradingPanel />
            <div className="mt-6">
                <PreviousResults module="grading" />
            </div>
        </>
    )
}
