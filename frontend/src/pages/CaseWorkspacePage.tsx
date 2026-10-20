import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ClipboardListIcon } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { getCase, listCaseImages } from "@/api/cases"
import { CaseAnalysisPanel } from "@/components/cases/CaseAnalysisPanel"
import { CaseDetailsForm } from "@/components/cases/CaseDetailsForm"
import { CaseHistory } from "@/components/cases/CaseHistory"
import { CaseImages } from "@/components/cases/CaseImages"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { CASES_PATH } from "@/lib/roles"
import { alertError } from "@/lib/styles"
import { cn } from "cn"

const TABS = [
    { id: "details", label: "Details" },
    { id: "images", label: "Images" },
    { id: "analyse", label: "Analyse" },
    { id: "history", label: "History" },
] as const
type Tab = (typeof TABS)[number]["id"]

/** One donor case: details entered once, its images, analyses on them, and every saved result. */
export function CaseWorkspacePage() {
    const { caseId = "" } = useParams()
    const [tab, setTab] = useState<Tab>("details")
    const donorCase = useQuery({ queryKey: ["case", caseId], queryFn: () => getCase(caseId) })
    const images = useQuery({ queryKey: ["case", caseId, "images"], queryFn: () => listCaseImages(caseId) })

    if (donorCase.isPending) return <Spinner />
    if (donorCase.isError) {
        return (
            <div className="space-y-3">
                <p role="alert" className={alertError}>{donorCase.error.message}</p>
                <Link to={CASES_PATH} className="text-sm font-medium text-accent hover:underline">Back to donor cases</Link>
            </div>
        )
    }

    const c = donorCase.data
    const imageList = images.data ?? []

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <ClipboardListIcon aria-hidden="true" />
                        <Link to={CASES_PATH} className="hover:underline">Donor cases</Link>
                    </>
                }
                title={`Tissue ${c.tissueId}`}
                description={`${c.tissueId.endsWith("R") ? "Right" : "Left"} eye · ${c.imageCount} ${c.imageCount === 1 ? "image" : "images"} · opened ${new Date(c.createdAt).toLocaleDateString("en-GB")}`}
            />

            <div role="tablist" aria-label="Case sections" className="mb-6 flex flex-wrap gap-2">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        type="button"
                        role="tab"
                        id={`case-tab-${t.id}`}
                        aria-selected={tab === t.id}
                        aria-controls={`case-panel-${t.id}`}
                        onClick={() => setTab(t.id)}
                        className={cn(
                            "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors",
                            tab === t.id ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card hover:bg-sunken",
                        )}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            <div role="tabpanel" id={`case-panel-${tab}`} aria-labelledby={`case-tab-${tab}`}>
                {tab === "details" && <CaseDetailsForm key={c.updatedAt} donorCase={c} />}
                {tab === "images" && (images.isPending ? <Spinner /> : <CaseImages caseId={c.id} images={imageList} />)}
                {tab === "analyse" && (images.isPending ? <Spinner /> : <CaseAnalysisPanel donorCase={c} images={imageList} />)}
                {tab === "history" && <CaseHistory caseId={c.id} images={imageList} />}
            </div>
        </>
    )
}
