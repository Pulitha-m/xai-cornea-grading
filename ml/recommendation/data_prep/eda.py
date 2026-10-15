"""Exploratory data analysis of the raw NEBSL workbook and the matching dataset.

Part A looks at the raw workbook (structure, missing values, grades, dates, outliers).
Part B checks that the ranking dataset was built correctly (one positive per request,
candidates genuinely available, no future information in the features).

Writes figures (PNG) and a markdown summary to outputs/eda/, for the report.
Only counts and summary statistics are written; no individual records, identifiers
or free-text notes are printed or saved.

From ml/:
    uv run python -m recommendation.data_prep.eda
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
import pandas as pd  # noqa: E402

from recommendation.config import load_config  # noqa: E402

# Reference palette (light mode): one categorical hue per series, recessive axes.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834"]  # slot 1 blue, slot 2 orange

FEATURES = [
    "Recipient_Age", "Recipient_Sex", "Recipient_Disease_Group", "Previous_Grafts",
    "Surgery_Type", "Indication_Type", "Request_Urgency", "Requested_Grade",
    "Recipient_Bed_Size_mm", "Cand_Tissue_Grade", "Cand_ECD", "Cand_CV", "Cand_HEX",
    "Cand_Donor_Age", "Cand_Donor_Disease", "Cand_Death_to_Preservation_h",
    "Cand_Serology_Clear", "Cand_Days_In_Storage", "Grade_Gap",
]

# Plausibility limits used only to flag values for review with NEBSL.
LIMITS = {"Cand_ECD": (1000, 4000), "Cand_CV": (15, 60), "Cand_HEX": (30, 80)}
DONOR_AGE_LIMITS = (2, 80)
CLEAN_GRADES = {"A+", "A", "B"}

# Columns that describe what happened after the decision. They must never be features.
OUTCOME_COLS = {"Label_Allocated", "Positive_Outside_Window", "Outcome_Grade_Request_Met"}


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=10)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))


def _figure(w: float = 7, h: float = 4):
    fig, ax = plt.subplots(figsize=(w, h), facecolor=SURFACE)
    return fig, ax


def _save(fig, out: Path, name: str) -> str:
    fig.tight_layout()
    path = out / name
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return name


def _bar_labels(ax, bars, fmt="{:.0f}") -> None:
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", color=INK_2, fontsize=8)


def raw_overview(raw_path: str, out: Path, figs: list) -> dict:
    """Part A: the raw workbook as received from NEBSL (counts only)."""
    raw = pd.read_excel(raw_path, sheet_name="Research Dataset")
    s = {"raw_rows": int(len(raw)), "raw_cols": int(raw.shape[1])}
    s["raw_dtypes"] = {str(k): int(v) for k, v in raw.dtypes.astype(str).value_counts().items()}
    miss = (raw.isna().mean() * 100).round(1)
    s["raw_fully_missing"] = int((miss == 100).sum())
    s["raw_missing_over_50"] = int((miss > 50).sum())
    s["raw_missing_top"] = miss.sort_values(ascending=False).head(15).to_dict()

    # Grade entries that are not a clean A+/A/B (transcription notes, conflicts)
    g = raw["Tissue_Grade"].dropna().astype(str).str.strip()
    s["grade_entries_not_clean"] = int((~g.isin(CLEAN_GRADES)).sum())
    s["grade_missing"] = int(raw["Tissue_Grade"].isna().sum())

    # Date coverage and date-order checks
    d = {c: pd.to_datetime(raw[c], errors="coerce") for c in
         ["Death_Date_Time", "Preservation_Date_Time", "Konan_Exam_Date", "Request_Date", "Surgery_Date"]}
    s["tissues_per_year"] = {int(k): int(v) for k, v in d["Konan_Exam_Date"].dt.year.value_counts().sort_index().items()}
    s["date_order_issues"] = {
        "preservation before death": int((d["Preservation_Date_Time"] < d["Death_Date_Time"]).sum()),
        "Konan exam before preservation day": int((d["Konan_Exam_Date"] < d["Preservation_Date_Time"].dt.normalize()).sum()),
        "surgery before preservation day": int((d["Surgery_Date"] < d["Preservation_Date_Time"].dt.normalize()).sum()),
        "request dated after surgery": int((d["Request_Date"] > d["Surgery_Date"]).sum()),
    }
    return s


def tissue_overview(dataset: str, out: Path, figs: list) -> dict:
    """Cleaned tissue table: grade distribution, measures, donor age outliers."""
    t = pd.read_excel(dataset, sheet_name="Tissues")
    s = {}
    grades = t["Tissue_Grade"].value_counts().reindex(["A+", "A", "B"]).fillna(0)
    fig, ax = _figure(6, 3.6)
    bars = ax.bar(grades.index, grades.values, color=SERIES[0], width=0.55)
    _bar_labels(ax, bars)
    _style(ax, "Tissue grade distribution (cleaned)", "Grade", "Corneas")
    figs.append(_save(fig, out, "07_grade_distribution.png"))
    s["grade_counts"] = {k: int(v) for k, v in grades.items()}
    s["grade_unknown_after_cleaning"] = int(t["Tissue_Grade"].isna().sum())

    years = pd.to_datetime(t["Konan_Exam_Date"]).dt.year.value_counts().sort_index()
    fig, ax = _figure()
    bars = ax.bar(years.index.astype(int).astype(str), years.values, color=SERIES[0], width=0.6)
    _bar_labels(ax, bars)
    _style(ax, "Corneas examined per year (Konan exam date)", "Year", "Corneas")
    figs.append(_save(fig, out, "08_tissues_per_year.png"))

    s["measures"] = {c: {k: round(float(v), 1) for k, v in t[c].describe()[["count", "mean", "std", "min", "50%", "max"]].items()}
                     for c in ["ECD", "CV", "HEX", "Donor_Age", "Death_to_Preservation_h"]}
    lo, hi = DONOR_AGE_LIMITS
    s["donor_age_outside"] = int(((t["Donor_Age"] < lo) | (t["Donor_Age"] > hi)).sum())
    return s


def validate_matching(dataset: str) -> dict:
    """Part B: is the ranking task built correctly? Each check returns a count of problems."""
    pairs = pd.read_excel(dataset, sheet_name="Ranking_Pairs")
    t = pd.read_excel(dataset, sheet_name="Tissues")
    for c in ["Ready_From", "Available_Until", "Allocated_On"]:
        t[c] = pd.to_datetime(t[c])
    pairs["Decision_Date"] = pd.to_datetime(pairs["Decision_Date"])
    m = pairs.merge(t[["Record_ID", "Ready_From", "Available_Until", "Allocated_On"]],
                    left_on="Candidate_Record_ID", right_on="Record_ID", how="left")
    neg = m[m["Label_Allocated"] == 0]
    pos_per_req = pairs.groupby("Request_ID")["Label_Allocated"].sum()
    checks = {
        "requests without exactly one allocated cornea": int((pos_per_req != 1).sum()),
        "duplicate request-candidate pairs": int(pairs.duplicated(["Request_ID", "Candidate_Record_ID"]).sum()),
        "allocated cornea outside the availability rules": int(pairs["Positive_Outside_Window"].fillna(0).astype(bool).sum()),
        "candidates not yet examined/ready at decision date": int((neg["Ready_From"] > neg["Decision_Date"]).sum()),
        "candidates past the storage window at decision date": int((neg["Available_Until"] < neg["Decision_Date"]).sum()),
        "candidates already allocated before decision date": int((neg["Allocated_On"] < neg["Decision_Date"]).sum()),
        "negative days in storage": int((pairs["Cand_Days_In_Storage"] < 0).sum()),
        "outcome columns used as features": len(OUTCOME_COLS & set(FEATURES)),
    }
    return checks


def run(dataset: str, out_dir: str, raw_path: str | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pairs = pd.read_excel(dataset, sheet_name="Ranking_Pairs")
    requests = pd.read_excel(dataset, sheet_name="Requests")
    figs, summary = [], {}
    if raw_path:
        summary.update(raw_overview(raw_path, out, figs))

    # 1. Candidates per request (how hard each ranking task is)
    pool = pairs.groupby("Request_ID").size()
    fig, ax = _figure()
    ax.hist(pool, bins=range(0, int(pool.max()) + 3, 2), color=SERIES[0], edgecolor=SURFACE, linewidth=2)
    _style(ax, "Candidate corneas available per request", "Candidates in the pool", "Requests")
    figs.append(_save(fig, out, "01_candidates_per_request.png"))
    summary["requests"] = int(pool.size)
    summary["pairs"] = int(len(pairs))
    summary["pool_mean"] = round(float(pool.mean()), 1)
    summary["pool_median"] = float(pool.median())
    summary["pool_min_max"] = (int(pool.min()), int(pool.max()))
    summary["positive_rate"] = round(float(pairs["Label_Allocated"].mean()), 3)

    # 2. Missing values per feature
    miss = (pairs[FEATURES].isna().mean() * 100).sort_values()
    fig, ax = _figure(7, 6)
    bars = ax.barh(miss.index, miss.values, color=SERIES[0], height=0.6)
    _style(ax, "Missing values per feature (% of training rows)", "% missing", "")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    for b in bars:
        ax.annotate(f"{b.get_width():.0f}%", (b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points", va="center", color=INK_2, fontsize=8)
    ax.set_xlim(0, 105)
    figs.append(_save(fig, out, "02_missing_values.png"))
    summary["missing_pct"] = miss.round(1).to_dict()

    # 3. Endothelial measures, one panel per measure (no shared or dual axis)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), facecolor=SURFACE)
    for ax, (col, label) in zip(axes, [("Cand_ECD", "ECD (cells/mm²)"), ("Cand_CV", "CV (%)"), ("Cand_HEX", "HEX (%)")]):
        vals = pairs.drop_duplicates("Candidate_Record_ID")[col].dropna()
        ax.hist(vals, bins=20, color=SERIES[0], edgecolor=SURFACE, linewidth=1.5)
        _style(ax, label, "", "Corneas" if col == "Cand_ECD" else "")
    figs.append(_save(fig, out, "03_endothelial_measures.png"))

    # 4. Requests per year (has practice changed over time?)
    years = pd.to_datetime(requests["Request_Date"]).dt.year.value_counts().sort_index()
    fig, ax = _figure()
    bars = ax.bar(years.index.astype(str), years.values, color=SERIES[0], width=0.6)
    _bar_labels(ax, bars)
    _style(ax, "Recipient requests per year", "Year", "Requests")
    figs.append(_save(fig, out, "04_requests_per_year.png"))
    summary["requests_per_year"] = {int(k): int(v) for k, v in years.items()}

    # 5. Grade gap: allocated vs not allocated (what does practice favour?)
    gap = pairs.dropna(subset=["Grade_Gap"])
    share = (gap.groupby("Label_Allocated")["Grade_Gap"].value_counts(normalize=True)
             .unstack(fill_value=0).T.sort_index() * 100)
    x = range(len(share.index))
    w = 0.38
    fig, ax = _figure()
    names = {0: "Not allocated", 1: "Allocated"}
    for i, lab in enumerate([0, 1]):
        bars = ax.bar([v + (i - 0.5) * (w + 0.02) for v in x], share.get(lab, 0), width=w,
                      color=SERIES[i], label=names[lab])
        _bar_labels(ax, bars, "{:.0f}%")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{int(g):+d}" if g else "0 (exact)" for g in share.index])
    _style(ax, "Grade gap of candidates: allocated vs not allocated",
           "Candidate grade minus requested grade", "% of candidates in group")
    ax.legend(frameon=False, labelcolor=INK_2, fontsize=9, loc="upper left")
    figs.append(_save(fig, out, "05_grade_gap_by_label.png"))
    summary["grade_gap_share_pct"] = share.round(1).to_dict()

    # 6. Outcome of the real allocations
    met = requests["Grade_Request_Met"].value_counts()
    fig, ax = _figure(6, 3.6)
    bars = ax.bar(met.index.astype(str), met.values, color=SERIES[0], width=0.55)
    _bar_labels(ax, bars)
    _style(ax, "Did the allocated cornea meet the requested grade?", "", "Requests")
    figs.append(_save(fig, out, "06_grade_request_met.png"))
    summary["grade_request_met"] = met.to_dict()

    # Outliers to review with NEBSL (counts only)
    tissues = pairs.drop_duplicates("Candidate_Record_ID")
    summary["outliers_for_review"] = {
        col: int(((tissues[col] < lo) | (tissues[col] > hi)).sum()) for col, (lo, hi) in LIMITS.items()
    }

    summary.update(tissue_overview(dataset, out, figs))
    summary["checks"] = validate_matching(dataset)
    _write_markdown(out / "eda_summary.md", summary, figs)
    return summary


def _write_markdown(path: Path, s: dict, figs: list[str]) -> None:
    lines = ["# Exploratory data analysis", ""]
    if "raw_rows" in s:
        lines += [
            "## A. Raw NEBSL workbook",
            f"- Records: **{s['raw_rows']}**; columns: **{s['raw_cols']}**",
            "- Column types: " + ", ".join(f"{k} {v}" for k, v in s["raw_dtypes"].items()),
            f"- Columns completely empty: {s['raw_fully_missing']}; more than 50% missing: {s['raw_missing_over_50']}",
            f"- Tissue grade missing: {s['grade_missing']}; grade entries that are not a clean A+/A/B "
            f"(transcription notes or conflicting forms): **{s['grade_entries_not_clean']}** (verify with NEBSL)",
            "",
            "Most-missing columns (%):",
            *[f"- {k}: {v}%" for k, v in s["raw_missing_top"].items()],
            "",
            "Corneas per year (Konan exam date):",
            *[f"- {y}: {n}" for y, n in s["tissues_per_year"].items()],
            "",
            "Date-order checks (records):",
            *[f"- {k}: {v}" for k, v in s["date_order_issues"].items()],
            "",
        ]
    lines += [
        "## Cleaned tissue table",
        "Grade counts: " + ", ".join(f"{k} {v}" for k, v in s["grade_counts"].items())
        + f"; unknown after cleaning {s['grade_unknown_after_cleaning']}",
        "",
        "| Measure | n | mean | sd | min | median | max |",
        "|---|---|---|---|---|---|---|",
        *[f"| {c} | {v['count']:.0f} | {v['mean']} | {v['std']} | {v['min']} | {v['50%']} | {v['max']} |"
          for c, v in s["measures"].items()],
        f"\nDonor age outside {DONOR_AGE_LIMITS[0]}–{DONOR_AGE_LIMITS[1]}: {s['donor_age_outside']}",
        "",
        "## B. Matching dataset correctness checks (0 = pass)",
        *[f"- {'PASS' if v == 0 else 'CHECK'}: {k}: {v}" for k, v in s["checks"].items()],
        "",
        "## Size and balance",
        f"- Requests: **{s['requests']}**; training pairs: **{s['pairs']}**",
        f"- Candidates per request: mean {s['pool_mean']}, median {s['pool_median']:.0f}, "
        f"range {s['pool_min_max'][0]}–{s['pool_min_max'][1]}",
        f"- Positive rate: {s['positive_rate']:.1%} (one allocated cornea per request), "
        "so this is a ranking problem, not plain classification",
        "",
        "## Requests per year",
        *[f"- {y}: {n}" for y, n in s["requests_per_year"].items()],
        "",
        "## Allocation outcome (requested grade met?)",
        *[f"- {k}: {v}" for k, v in s["grade_request_met"].items()],
        "",
        "## Missing values (% of training rows)",
        *[f"- {k}: {v}%" for k, v in sorted(s["missing_pct"].items(), key=lambda kv: -kv[1]) if v > 0],
        "",
        "## Values outside plausible ranges (review with NEBSL)",
        *[f"- {k} outside {LIMITS[k][0]}–{LIMITS[k][1]}: {v} corneas" for k, v in s["outliers_for_review"].items()],
        "",
        "## Figures",
        *[f"![{f}]({f})" for f in figs],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="EDA for the matching dataset")
    ap.add_argument("--dataset", default=cfg["paths"]["matching_dataset"])
    ap.add_argument("--raw", default=cfg["paths"]["raw_workbook"])
    ap.add_argument("--out", default=str(Path(cfg["paths"]["outputs"]) / "eda"))
    a = ap.parse_args()
    raw = a.raw if Path(a.raw).exists() else None
    s = run(a.dataset, a.out, raw)
    if "raw_rows" in s:
        print(f"Raw workbook: {s['raw_rows']} records, {s['raw_cols']} columns")
    print(f"Requests {s['requests']}, pairs {s['pairs']}, mean pool {s['pool_mean']}")
    failed = {k: v for k, v in s["checks"].items() if v}
    print("Correctness checks: all passed" if not failed else f"Correctness checks to review: {failed}")
    print(f"Saved figures and eda_summary.md to {a.out}")


if __name__ == "__main__":
    main()
