"""One report with the output of every stage of the donor-matching work.

Runs each stage in order and collects its key output into a single self-contained
HTML page (charts embedded), for supervisors, panels and the thesis:

  1. Raw NEBSL data          what was received
  2. Matching dataset        how the ranking pairs were built
  3. Dataset checks + EDA    is it correct, what does practice favour
  4. Features                the 23 model inputs, chosen vs not chosen
  5. MCDA baseline           rule-based ranking vs random and grade-only
  6. ML ranker               model selection and three evaluations
  7. SHAP explanations       what drives the ranking, "Why #1?" examples
  8. Model analysis          ablation, learning curve, subgroups, errors
  9. Counterfactuals         what would make a cornea #1

Only summaries are shown (counts, means, metrics, study codes). The report is
written to outputs/report/ which is git-ignored.

From ml/:
    uv run python -m recommendation.main report
"""
import base64
import html
from datetime import date
from pathlib import Path

import pandas as pd

from recommendation import pipeline
from recommendation.data_prep import eda
from recommendation.matching.features import FEATURE_GROUPS, build_features

CSS = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--accent:#2a78d6;--ok:#2e7d4f;--bad:#b3261e}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 6px;padding-top:16px;border-top:1px solid var(--grid)}
h3{font-size:15px;margin:20px 0 6px;color:var(--ink2)}
.sub{color:var(--muted);margin:0 0 20px}.what{color:var(--ink2);margin:0 0 12px}
table{border-collapse:collapse;margin:8px 0 14px;font-size:13.5px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--grid);padding:5px 10px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
tr.hl td{font-weight:700}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 14px}
.kpi{border:1px solid var(--grid);border-radius:8px;padding:8px 14px;min-width:120px}
.kpi b{display:block;font-size:20px}.kpi span{color:var(--muted);font-size:12.5px}
.pass{color:var(--ok);font-weight:600}.fail{color:var(--bad);font-weight:600}
img{max-width:100%;border:1px solid var(--grid);border-radius:6px;margin:6px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.note{background:#f3f2ee;border-radius:6px;padding:10px 14px;color:var(--ink2);font-size:13.5px}
ul{margin:6px 0 12px}
"""


def _img(path: Path) -> str:
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img alt="{html.escape(path.stem)}" src="data:image/png;base64,{data}">'


def _table(df: pd.DataFrame, highlight: str | None = None, fmt: str = "{:.3f}") -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in [df.index.name or ""] + list(df.columns))
    whole = {"requests", "count"}  # columns shown without decimals

    def cell(col, v):
        if isinstance(v, float) and col in whole and v.is_integer():
            return f"{int(v):,}"
        return fmt.format(v) if isinstance(v, float) else html.escape(str(v))

    rows = []
    for idx, r in df.iterrows():
        cells = "".join(f"<td>{cell(c, v)}</td>" for c, v in r.items())
        cls = ' class="hl"' if highlight and str(idx) == highlight else ""
        rows.append(f"<tr{cls}><td>{html.escape(str(idx))}</td>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _kpis(items: list[tuple[str, str]]) -> str:
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>' for k, v in items
    ) + "</div>"


def _section(n: int, title: str, what: str, body: str) -> str:
    return f'<h2>Stage {n}. {html.escape(title)}</h2><p class="what">{html.escape(what)}</p>{body}'


def build_report(cfg: dict) -> tuple[Path, list[str]]:
    paths = cfg["paths"]
    outputs = Path(paths["outputs"])
    dataset = paths["matching_dataset"]
    log, parts = [], []

    # Stage 1-3: raw data, build notes, checks and EDA
    eda_dir = outputs / "eda"
    s = eda.run(dataset, str(eda_dir), raw_path=paths["raw_workbook"])
    miss = pd.DataFrame({"% missing": pd.Series(s["raw_missing_top"])}).head(8)
    miss.index.name = "column"
    measures = pd.DataFrame(s["measures"]).T.rename(columns={"50%": "median"})
    measures.index.name = "measure"
    body = _kpis([("records", str(s["raw_rows"])), ("columns", str(s["raw_cols"])),
                  ("grade A+ / A / B", " / ".join(str(v) for v in s["grade_counts"].values())),
                  ("columns > 50% missing", str(s["raw_missing_over_50"])),
                  ("grade entries to verify", str(s["grade_entries_not_clean"]))])
    body += "<h3>Most-missing columns</h3>" + _table(miss, fmt="{:.1f}")
    body += "<h3>Cleaned tissue measures</h3>" + _table(measures, fmt="{:.1f}")
    body += '<div class="grid2">' + _img(eda_dir / "07_grade_distribution.png") \
            + _img(eda_dir / "08_tissues_per_year.png") + "</div>"
    parts.append(_section(1, "Raw NEBSL data",
                          "The workbook as received: size, completeness and tissue quality.", body))
    log.append(f"Stage 1 raw data: {s['raw_rows']} records, {s['raw_cols']} columns")

    notes = pd.read_excel(dataset, sheet_name="Build_Notes").set_index("Item")
    notes.index.name = "item"
    body = _kpis([("requests", str(s["requests"])), ("ranking pairs", f"{s['pairs']:,}"),
                  ("candidates per request", f"{s['pool_mean']} (median {s['pool_median']:.0f})"),
                  ("positive rate", f"{s['positive_rate']:.1%}"), ("synthetic rows", "0")])
    body += _table(notes)
    parts.append(_section(2, "Matching dataset",
                          "Each real request is paired with every cornea genuinely available on its "
                          "decision date; the cornea actually allocated is labelled 1.", body))
    log.append(f"Stage 2 matching dataset: {s['requests']} requests, {s['pairs']} pairs")

    checks = "".join(
        f"<li><span class='{'pass' if v == 0 else 'fail'}'>{'PASS' if v == 0 else 'CHECK'}</span> "
        f"{html.escape(k)}: {v}</li>" for k, v in s["checks"].items())
    n_fail = sum(v != 0 for v in s["checks"].values())
    body = f"<h3>Correctness checks (0 = pass)</h3><ul>{checks}</ul>"
    body += '<div class="grid2">' + "".join(_img(eda_dir / f) for f in [
        "05_grade_gap_by_label.png", "01_candidates_per_request.png",
        "03_endothelial_measures.png", "04_requests_per_year.png"]) + "</div>"
    parts.append(_section(3, "Dataset checks and EDA",
                          "Proof that the ranking task is built correctly, and what past allocations favour.",
                          body))
    log.append("Stage 3 checks: " + ("all passed" if n_fail == 0 else f"{n_fail} to review"))

    # Stage 4: features
    pairs = pd.read_excel(dataset, sheet_name="Ranking_Pairs")
    X = build_features(pairs)
    chosen = pairs["Label_Allocated"] == 1
    rows = []
    for group, cols in FEATURE_GROUPS.items():
        for c in cols:
            rows.append({"feature": c, "group": group, "chosen": X.loc[chosen, c].mean(),
                         "not chosen": X.loc[~chosen, c].mean(), "% missing": X[c].isna().mean() * 100})
    feats = pd.DataFrame(rows).set_index("feature")
    body = _kpis([("features", str(X.shape[1])), ("groups", str(len(FEATURE_GROUPS))),
                  ("rows", f"{len(X):,}")]) + _table(feats, fmt="{:.2f}")
    parts.append(_section(4, "Features",
                          "The 23 model inputs, with their average for chosen vs not-chosen corneas.", body))
    log.append(f"Stage 4 features: {X.shape[1]} features")

    # Stage 5: MCDA baseline
    mc = pipeline.run_matching(cfg, rebuild=False)
    cols = ["requests", "top1", "top3", "mrr", "ndcg@3"]
    t5 = pd.DataFrame(mc["test_requests"]).T[cols]
    a5 = pd.DataFrame(mc["all_requests"]).T[cols]
    w = pd.DataFrame({"weight": pd.Series(mc["weights"])})
    w.index.name = "criterion"
    body = "<h3>Held-out test requests</h3>" + _table(t5, highlight="MCDA")
    body += "<h3>All requests</h3>" + _table(a5, highlight="MCDA")
    body += f"<h3>Weights ({html.escape(mc['weights_version'])})</h3>" + _table(w, fmt="{:.2f}")
    parts.append(_section(5, "MCDA baseline",
                          "Rule-based score from grade fit, endothelium, freshness, donor age and "
                          "preservation time; compared with random order and a grade-only rule.", body))
    log.append(f"Stage 5 MCDA: test top-3 {t5.loc['MCDA', 'top3']:.3f}")

    # Stage 6: ML ranker
    rk = pipeline.run_ranker(cfg)
    sel = pd.DataFrame(rk["model_selection_cv"]).set_index("settings")[["cv_top1", "cv_top3", "cv_mrr"]]
    held = pd.DataFrame(rk["held_out_test"]).T[cols]
    rc = rk["repeated_cv_all_requests"]
    rep = pd.DataFrame(rc["methods"]).T[["top1", "top3", "mrr"]]
    ts = {k: v for k, v in rk["time_split_2024_to_2025"].items() if isinstance(v, dict)}
    tsd = pd.DataFrame(ts).T[["requests", "top1", "top3", "mrr"]]
    d3, dm = rc["difference"]["top3"], rc["difference"]["mrr"]
    body = _kpis([("selected model", f"{rk['selected_model']['model']}"),
                  ("top-3 vs MCDA (all requests)", f"{d3['ml_minus_mcda']:+.3f}"),
                  ("95% CI", f"{d3['ci95'][0]:+.3f} to {d3['ci95'][1]:+.3f}"),
                  ("MRR vs MCDA", f"{dm['ml_minus_mcda']:+.3f}")])
    body += "<h3>a. Model selection (5-fold grouped CV, training requests only)</h3>" + _table(sel)
    body += "<h3>b. Held-out test requests</h3>" + _table(held, highlight="ML ranker")
    body += (f"<h3>c. All {rc['requests']} requests, {rc['repeats']}× {rc['folds']}-fold grouped CV "
             "(main result)</h3>") + _table(rep, highlight="ML ranker")
    body += (f"<h3>d. Time split: train up to 2024 "
             f"({rk['time_split_2024_to_2025']['train_requests']} requests), test 2025</h3>") \
            + _table(tsd, highlight="ML ranker")
    body += ('<p class="note">These metrics measure agreement with past NEBSL allocations, '
             "not transplant outcomes.</p>")
    parts.append(_section(6, "ML ranker",
                          "A model learns from past allocations which available cornea was chosen. "
                          "Two model types are compared and the best is chosen on training requests only.",
                          body))
    log.append(f"Stage 6 ML ranker: {rk['selected_model']}, all-requests top-3 "
               f"{rc['methods']['ML ranker']['top3']:.3f} vs MCDA {rc['methods']['MCDA']['top3']:.3f}")

    # Stage 7: SHAP
    ex = pipeline.run_explain(cfg)
    body = _img(outputs / "explain" / "shap_global_reasons.png")
    for e in ex["examples"]:
        body += (f"<h3>{html.escape(e['request'])}: wants {html.escape(str(e['requested_grade']))}, "
                 f"{html.escape(str(e['surgery']))}, {e['pool']} candidates "
                 f"(allocated cornea ranked #{e['allocated_rank']:.0f})</h3><ul>")
        for c in e["top3"]:
            tag = " <b>← allocated</b>" if c["Label_Allocated"] == 1 else ""
            body += (f"<li>#{c['ML_Rank']:.0f} {html.escape(c['Candidate_Record_ID'])} "
                     f"(grade {html.escape(str(c['Cand_Tissue_Grade']))}, "
                     f"{c['Cand_Days_In_Storage']} d in storage): {html.escape(c['Why'])}{tag}</li>")
        body += "</ul>"
    body += ('<p class="note">Numbers compare each cornea with the other candidates for the same '
             "request (+ pushes it up the list). They describe the model, not clinical cause.</p>")
    parts.append(_section(7, "SHAP explanations",
                          "What changes the order of candidates, and a 'Why #1?' reason for each cornea.",
                          body))
    top = max(ex["reason_importance"], key=ex["reason_importance"].get)
    log.append(f"Stage 7 SHAP: strongest reason '{top}'")

    # Stage 8: model analysis
    an = pipeline.run_analysis(cfg)
    abl = pd.DataFrame(an["ablation"]).T[["top3", "mrr", "mrr_change"]]
    curve = pd.DataFrame(an["learning_curve"]).set_index("train_requests")[["ml_top3", "ml_mrr", "mcda_mrr"]]
    sub = pd.DataFrame(an["subgroups"]).set_index(["subgroup", "level"])
    sub.index = [f"{a}: {b}" for a, b in sub.index]
    sub.index.name = "subgroup"
    e = an["errors"]
    comp = pd.DataFrame(e["comparison"]).T
    adir = outputs / "analysis"
    body = '<div class="grid2">' + _img(adir / "ablation.png") + _img(adir / "learning_curve.png") + "</div>"
    body += "<h3>a. Ablation: remove one factor at a time</h3>" + _table(abl, highlight="all features")
    body += "<h3>b. Learning curve</h3>" + _table(curve)
    body += "<h3>c. Subgroups (ML vs MCDA)</h3>" + _table(sub)
    body += (f"<h3>d. Errors: allocated cornea ranked below #5 in {e['missed']} of {e['requests']} "
             f"requests ({e['missed_share']:.0%})</h3>") + _table(comp, fmt="{:.2f}")
    body += ('<p class="note">Where the model misses, the cornea actually chosen was more often a lower '
             "grade and older than the model's #1, which suggests the clinician used information not in "
             "the data (e.g. surgeon preference, timing or logistics).</p>")
    parts.append(_section(8, "Model analysis",
                          "Which factors matter, whether more data would help, where the model works "
                          "best and where it fails (repeated grouped cross-validation).", body))
    worst = abl["mrr_change"].drop("all features").idxmin().replace("without ", "")
    log.append(f"Stage 8 analysis: most important factor '{worst}', "
               f"{e['missed']} of {e['requests']} requests missed")

    # Stage 9: counterfactual explanations
    cf = pipeline.run_counterfactual(cfg)
    summ = cf["summary"]
    body = ""
    for ex in cf["examples"]:
        body += (f"<h3>{html.escape(ex['request'])} (actually allocated: {html.escape(ex['allocated'])})</h3><ul>"
                 + "".join(f"<li>{html.escape(x)}</li>" for x in ex["lines"]) + "</ul>")
    oc = pd.DataFrame({"requests": pd.Series(summ["outcome"])})
    oc.index.name = "allocated cornea vs model #1"
    kd = pd.DataFrame({"requests": pd.Series(summ["actionable_kinds"])})
    kd.index.name = "actionable change that was enough"
    body += f"<h3>All {summ['requests']} requests</h3>" + _table(oc, fmt="{:.0f}") + _table(kd, fmt="{:.0f}")
    if summ["median_days_fewer"] is not None:
        body += f"<p>Median days fewer in storage needed: <b>{summ['median_days_fewer']:.0f}</b></p>"
    body += ('<p class="note">Actionable = the eye bank can act on it (complete serology, '
             "allocate sooner). Descriptive = a property of the tissue, shown only to explain. "
             "Other features are held fixed and the whole pool is re-scored.</p>")
    parts.append(_section(9, "Counterfactual explanations",
                          "The smallest realistic change that would make a cornea rank #1.", body))
    act = summ["outcome"]["actionable change"]
    log.append(f"Stage 9 counterfactuals: {act} of {summ['requests']} allocated corneas "
               "reach #1 with an actionable change")

    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Donor Matching Stages</title><style>{CSS}</style></head><body><main>"
            f"<h1>Donor–recipient matching: output of each stage</h1>"
            f"<p class='sub'>iTRUST Member 4 · generated {date.today():%d %b %Y} · summaries only, "
            f"no patient records</p>{''.join(parts)}</main></body></html>")
    out = outputs / "report"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "stage_report.html"
    path.write_text(page, encoding="utf-8")
    return path, log
