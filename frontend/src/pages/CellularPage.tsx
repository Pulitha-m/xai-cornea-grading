import { HexagonIcon } from "lucide-react"
import { PreviousResults } from "@/components/cases/PreviousResults"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { CellularPanel } from "@/components/cellular/CellularPanel"

export function CellularPage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <HexagonIcon aria-hidden="true" />
                        AI intelligence
                    </>
                }
                title="Cellular analysis"
                description="Selects the analysable region of a specular microscopy image, segments the endothelial cells and measures cell density (ECD), size variation (CV) and hexagonality (HEX), with their uncertainty and a reliability rating for every cell. Research tool — not a clinical measurement."
            />
            <CellularPanel />
            <div className="mt-6">
                <PreviousResults module="cellular" />
            </div>
        </>
    )
}
