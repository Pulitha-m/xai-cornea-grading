"""End-to-end pipelines for the recommendation module.

Implemented:
    run_matching   build matching dataset -> MCDA ranking -> evaluation
    run_ranker     train the ML ranker on the same split and compare it with MCDA
    run_explain    SHAP explanations for the trained ranker (global + "Why #1?")
    run_analysis   ablation, learning curve, subgroup and error analysis of the ranker
    run_counterfactual  "what would make this cornea #1?" for examples and all missed requests

Part B (post-transplant follow-up; simulated cohort until real follow-up data arrives):
    run_followup_eda   P1: data checks, ECD trends, Kaplan-Meier survival, visits, rejection
    run_followup_dataset  P2: 12-month landmark dataset, split by graft, train-only preprocessing
    run_followup_baselines  P3: trajectory baselines (MAE/RMSE) and risk baselines (C-index, AUC, Brier)
    run_trajectory     P4: GBM and LSTM vs baselines, learning curve, test once, save the chosen model
    run_risk           P5: Cox, gradient-boosted Cox, DeepSurv per endpoint, calibration, test once
    run_followup_explain  P6: SHAP reasons and counterfactuals for trajectory and risk
    run_followup       planned (P7)
"""
import json
from pathlib import Path

import pandas as pd

from recommendation.data_prep.build_matching_dataset import build
from recommendation.evaluation.metrics import compare
from recommendation.evaluation.split import grouped_split
from recommendation.matching.mcda import Weights, score


def run_matching(cfg: dict, rebuild: bool = True) -> dict:
    paths, split, m = cfg["paths"], cfg["split"], cfg["matching"]

    dataset = Path(paths["matching_dataset"])
    if rebuild or not dataset.exists():
        dataset.parent.mkdir(parents=True, exist_ok=True)
        build(paths["raw_workbook"], str(dataset), storage_days=m["storage_days"])
    pairs = pd.read_excel(dataset, sheet_name="Ranking_Pairs")

    weights = Weights(**m["weights"])
    scored = score(pairs, weights)
    _, test = grouped_split(scored, group_col=split["group_col"],
                            test_size=split["test_size"], seed=split["seed"])

    results = {
        "weights_version": m["weights_version"],
        "weights": weights.normalised(),
        "split": split,
        "all_requests": compare(scored).round(4).to_dict(orient="index"),
        "test_requests": compare(test).round(4).to_dict(orient="index"),
    }
    out = Path(paths["outputs"]) / "matching"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(results, indent=2))
    return results


def run_ranker(cfg: dict) -> dict:
    """Select, train and evaluate the ML ranker; save the model and its metrics.

    Three evaluations, all by whole requests:
      1. held-out test requests (same 80/20 split as MCDA)
      2. repeated 5-fold grouped CV over all requests, with a bootstrap interval
      3. time-based: train on requests up to 2024, test on 2025
    """
    import joblib

    from recommendation.evaluation.metrics import grade_only_rank, random_baseline, ranking_metrics
    from recommendation.matching.features import FEATURES
    from recommendation.matching.ranker import Ranker, repeated_cv_comparison, select

    paths, split, m = cfg["paths"], cfg["split"], cfg["matching"]
    seed = split["seed"]
    pairs = pd.read_excel(paths["matching_dataset"], sheet_name="Ranking_Pairs")
    scored = score(pairs, Weights(**m["weights"]))
    train, test = grouped_split(scored, group_col=split["group_col"],
                                test_size=split["test_size"], seed=seed)

    # 1. choose the model on training requests only, then test once
    best, cv_table = select(train, seed=seed)
    model = Ranker(best).fit(train, seed)
    test = model.rank(test)
    held_out = compare(test).round(4).to_dict(orient="index")
    held_out["ML ranker"] = {k: round(v, 4) for k, v in ranking_metrics(test, "ML_Rank").items()}

    # 2. repeated grouped CV over all requests
    repeated = repeated_cv_comparison(scored, best, seed=seed)

    # 3. time-based check
    year = pd.to_datetime(scored["Request_Date"]).dt.year
    early, late = scored[year <= 2024], scored[year == 2025].copy()
    late = Ranker(best).fit(early, seed).rank(late)
    late["Grade_Rank"] = grade_only_rank(late)
    time_split = {
        "train_requests": int(early["Request_ID"].nunique()),
        "Random (expected)": {k: round(v, 4) for k, v in random_baseline(late).items()},
        "Grade-only rule": {k: round(v, 4) for k, v in ranking_metrics(late, "Grade_Rank").items()},
        "MCDA": {k: round(v, 4) for k, v in ranking_metrics(late, "MCDA_Rank").items()},
        "ML ranker": {k: round(v, 4) for k, v in ranking_metrics(late, "ML_Rank").items()},
    }

    # final model for the app: trained on all requests
    final = Ranker(best).fit(scored, seed)
    models = Path(paths["models"])
    models.mkdir(parents=True, exist_ok=True)
    joblib.dump({"settings": best, "features": FEATURES, "estimator": final.estimator},
                models / "matching_ranker.joblib")

    weights = final.weights()
    results = {
        "selected_model": best,
        "model_selection_cv": cv_table.assign(settings=cv_table["settings"].astype(str))
                                      .to_dict(orient="records"),
        "held_out_test": held_out,
        "repeated_cv_all_requests": repeated,
        "time_split_2024_to_2025": time_split,
        "feature_weights": None if weights is None else weights.round(4).to_dict(),
    }
    out = Path(paths["outputs"]) / "matching"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranker_metrics.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def run_explain(cfg: dict, n_examples: int = 3) -> dict:
    """Explain the saved ranker with SHAP; write a chart, a summary and a table.

    Run ``ranker`` first: this loads models/matching_ranker.joblib.
    """
    import joblib
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from recommendation.explain.shap_explain import explain_ranking, global_importance, shap_values
    from recommendation.matching.ranker import Ranker

    paths, split = cfg["paths"], cfg["split"]
    model_file = Path(paths["models"]) / "matching_ranker.joblib"
    if not model_file.exists():
        raise FileNotFoundError(f"{model_file} not found. Run 'ranker' first.")
    saved = joblib.load(model_file)
    ranker = Ranker(saved["settings"], saved["estimator"])

    pairs = pd.read_excel(paths["matching_dataset"], sheet_name="Ranking_Pairs")
    out = Path(paths["outputs"]) / "explain"
    out.mkdir(parents=True, exist_ok=True)

    # Global importance
    values = shap_values(ranker, pairs, background=pairs)
    feat_imp, reason_imp = global_importance(values, pairs["Request_ID"])

    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor="#fcfcfb")
    r = reason_imp.sort_values()
    bars = ax.barh(r.index, r.values * 100, color="#2a78d6", height=0.6)
    for b in bars:
        ax.annotate(f"{b.get_width():.0f}%", (b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points", va="center", color="#52514e", fontsize=8)
    ax.set_title("What changes the ML ranking within a request (share of |SHAP|)", loc="left",
                 color="#0b0b0b", fontsize=11, fontweight="bold")
    ax.set_facecolor("#fcfcfb")
    ax.tick_params(colors="#898781", length=0)
    ax.grid(axis="x", color="#e1e0d9")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_xlim(0, r.max() * 115)
    fig.tight_layout()
    fig.savefig(out / "shap_global_reasons.png", dpi=150, facecolor="#fcfcfb")
    plt.close(fig)

    # Local "Why #1?" for every candidate
    explained = explain_ranking(ranker, pairs, background=pairs)
    keep = ["Request_ID", "Requested_Grade", "Surgery_Type", "Candidate_Record_ID",
            "Cand_Tissue_Grade", "Cand_ECD", "Cand_Days_In_Storage", "Cand_Serology_Clear",
            "ML_Rank", "Label_Allocated", "Why"]
    explained.sort_values(["Request_ID", "ML_Rank"])[keep].to_excel(out / "explanations.xlsx", index=False)

    # Worked examples from the held-out test requests
    _, test = grouped_split(pairs, group_col=split["group_col"],
                            test_size=split["test_size"], seed=split["seed"])
    examples = []
    for rid in sorted(test["Request_ID"].unique())[:n_examples]:
        e = explained[explained["Request_ID"] == rid].sort_values("ML_Rank")
        examples.append({
            "request": rid,
            "requested_grade": e["Requested_Grade"].iloc[0],
            "surgery": e["Surgery_Type"].iloc[0],
            "pool": int(len(e)),
            "allocated_rank": float(e.loc[e["Label_Allocated"] == 1, "ML_Rank"].iloc[0]),
            "top3": e.head(3)[["ML_Rank", "Candidate_Record_ID", "Cand_Tissue_Grade",
                               "Cand_Days_In_Storage", "Label_Allocated", "Why"]].to_dict("records"),
        })

    _write_explain_md(out / "shap_summary.md", saved["settings"], feat_imp, reason_imp, examples)
    return {"reason_importance": reason_imp.round(4).to_dict(),
            "feature_importance": feat_imp.head(10).round(4).to_dict(),
            "examples": examples}


def _write_explain_md(path: Path, settings, feat_imp, reason_imp, examples) -> None:
    lines = ["# SHAP explanations of the ML ranker", "",
             f"Model: {settings}", "",
             "Explanations describe what drove the model's ranking, learned from past NEBSL",
             "allocations. They are not proof of clinical cause.", "",
             "## What changes the order of candidates (share of |SHAP|, relative to each pool)", ""]
    lines += [f"- {k}: {v:.0%}" for k, v in reason_imp.items()]
    lines += ["", "## Top 10 individual features", ""]
    lines += [f"- {k}: {v:.1%}" for k, v in feat_imp.head(10).items()]
    lines += ["", "## Worked examples (held-out test requests)", "",
              "Numbers in brackets: contribution compared with the other candidates for the",
              "same request (+ pushes the cornea up, - pushes it down).", ""]
    for ex in examples:
        lines += [f"### {ex['request']}: wants grade {ex['requested_grade']}, {ex['surgery']}, "
                  f"{ex['pool']} candidates; actually allocated cornea ranked #{ex['allocated_rank']:.0f}", ""]
        for c in ex["top3"]:
            tag = "  <- allocated" if c["Label_Allocated"] == 1 else ""
            lines.append(f"- #{c['ML_Rank']:.0f} {c['Candidate_Record_ID']} (grade {c['Cand_Tissue_Grade']}, "
                         f"{c['Cand_Days_In_Storage']} d in storage): {c['Why']}{tag}")
        lines.append("")
    lines += ["![reasons](shap_global_reasons.png)"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_analysis(cfg: dict, repeats: int = 5) -> dict:
    """Ablation, learning curve, subgroups and errors; charts + summary in outputs/analysis/."""
    import joblib
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from recommendation.evaluation import analysis as A

    paths, m, seed = cfg["paths"], cfg["matching"], cfg["split"]["seed"]
    model_file = Path(paths["models"]) / "matching_ranker.joblib"
    settings = joblib.load(model_file)["settings"] if model_file.exists() else {"model": "logistic", "C": 1.0}
    pairs = pd.read_excel(paths["matching_dataset"], sheet_name="Ranking_Pairs")
    scored = score(pairs, Weights(**m["weights"]))
    kw = {"repeats": repeats, "seed": seed}

    abl = A.ablation(scored, settings, **kw)
    curve = A.learning_curve(scored, settings, **kw)
    ranks = A.cv_ranks(scored, settings, **kw)
    sub = A.subgroups(scored, ranks)
    err = A.errors(scored, ranks, settings)

    out = Path(paths["outputs"]) / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    ink, ink2, muted, grid, base, bg = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
    blue, orange = "#2a78d6", "#eb6834"

    def style(ax, title, xlabel, ylabel):
        ax.set_facecolor(bg)
        ax.set_title(title, loc="left", color=ink, fontsize=11, fontweight="bold")
        ax.set_xlabel(xlabel, color=ink2)
        ax.set_ylabel(ylabel, color=ink2)
        ax.tick_params(colors=muted, length=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(base)

    # Ablation: how much MRR drops without each reason
    drop = (-abl["mrr_change"].drop("all features")).sort_values()
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=bg)
    bars = ax.barh([i.replace("without ", "") for i in drop.index], drop.values, color=blue, height=0.6)
    for b in bars:
        ax.annotate(f"{b.get_width():+.3f}", (max(b.get_width(), 0), b.get_y() + b.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points", va="center", color=ink2, fontsize=8)
    ax.grid(axis="x", color=grid)
    ax.set_xlim(min(0, drop.min()) * 1.2, drop.max() * 1.3 + 0.002)
    style(ax, "Ablation: MRR lost when a factor is removed", "Drop in MRR (higher = factor matters more)", "")
    fig.tight_layout()
    fig.savefig(out / "ablation.png", dpi=150, facecolor=bg)
    plt.close(fig)

    # Learning curve: ML vs MCDA as training data grows
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=bg)
    ax.plot(curve["train_requests"], curve["ml_mrr"], color=blue, marker="o", linewidth=2, label="ML ranker")
    ax.plot(curve["train_requests"], curve["mcda_mrr"], color=orange, linewidth=2, linestyle="--",
            label="MCDA (no training)")
    for x, y in zip(curve["train_requests"], curve["ml_mrr"]):
        ax.annotate(f"{y:.3f}", (x, y), xytext=(0, 7), textcoords="offset points", ha="center",
                    color=ink2, fontsize=8)
    ax.grid(axis="y", color=grid)
    ax.set_xticks(curve["train_requests"])
    ax.legend(frameon=False, labelcolor=ink2, fontsize=9, loc="upper left")
    style(ax, "Learning curve: does more data help?", "Training requests", "MRR")
    fig.tight_layout()
    fig.savefig(out / "learning_curve.png", dpi=150, facecolor=bg)
    plt.close(fig)

    results = {
        "settings": settings, "repeats": repeats,
        "ablation": abl.round(4).to_dict(orient="index"),
        "learning_curve": curve.round(4).to_dict(orient="records"),
        "subgroups": sub.round(4).to_dict(orient="records"),
        "errors": {k: v for k, v in err.items() if k != "comparison"}
                  | {"comparison": err["comparison"].round(2).to_dict(orient="index")},
    }
    (out / "analysis.json").write_text(json.dumps(results, indent=2, default=str))
    _write_analysis_md(out / "analysis_summary.md", abl, curve, sub, err)
    return results


def _write_analysis_md(path: Path, abl, curve, sub, err) -> None:
    f3 = "{:.3f}".format
    lines = ["# Model analysis of the ML ranker", "",
             "Repeated 5-fold grouped cross-validation over all requests.", "",
             "## 1. Ablation (remove one factor at a time)", "",
             "| model | top-3 | MRR | MRR change |", "|---|---|---|---|"]
    lines += [f"| {i} | {f3(r.top3)} | {f3(r.mrr)} | {r.mrr_change:+.3f} |" for i, r in abl.iterrows()]
    lines += ["", "## 2. Learning curve", "",
              "| training requests | ML top-3 | ML MRR | MCDA MRR |", "|---|---|---|---|"]
    lines += [f"| {int(r.train_requests)} | {f3(r.ml_top3)} | {f3(r.ml_mrr)} | {f3(r.mcda_mrr)} |"
              for r in curve.itertuples()]
    lines += ["", "## 3. Subgroups", "",
              "| subgroup | level | requests | ML top-3 | MCDA top-3 | ML MRR | MCDA MRR |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {r.subgroup} | {r.level} | {r.requests} | {f3(r.ml_top3)} | {f3(r.mcda_top3)} | "
              f"{f3(r.ml_mrr)} | {f3(r.mcda_mrr)} |" for r in sub.itertuples()]
    lines += ["", "## 4. Errors", "",
              f"Requests where the allocated cornea ranked below #5 on average: "
              f"**{err['missed']} of {err['requests']}** ({err['missed_share']:.0%}).", "",
              "| (mean over missed requests) | allocated cornea | model's #1 |", "|---|---|---|"]
    lines += [f"| {i} | {r.iloc[0]:.2f} | {r.iloc[1]:.2f} |" for i, r in err["comparison"].iterrows()]
    lines += ["", "![ablation](ablation.png)", "", "![learning curve](learning_curve.png)"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_counterfactual(cfg: dict, n_examples: int = 3) -> dict:
    """Counterfactual explanations from the saved ranker; summary in outputs/explain/."""
    import joblib

    from recommendation.explain.counterfactual import counterfactuals, describe, summarise_misses
    from recommendation.matching.ranker import Ranker

    paths, split = cfg["paths"], cfg["split"]
    model_file = Path(paths["models"]) / "matching_ranker.joblib"
    if not model_file.exists():
        raise FileNotFoundError(f"{model_file} not found. Run 'ranker' first.")
    saved = joblib.load(model_file)
    ranker = Ranker(saved["settings"], saved["estimator"])
    pairs = pd.read_excel(paths["matching_dataset"], sheet_name="Ranking_Pairs")

    # Worked examples: the same held-out test requests as the SHAP examples
    _, test = grouped_split(pairs, group_col=split["group_col"],
                            test_size=split["test_size"], seed=split["seed"])
    examples = []
    for rid in sorted(test["Request_ID"].unique())[:n_examples]:
        pool = pairs[pairs["Request_ID"] == rid]
        ranked = ranker.rank(pool).sort_values("ML_Rank")
        ids = list(ranked.head(3)["Candidate_Record_ID"])
        allocated = ranked.loc[ranked["Label_Allocated"] == 1, "Candidate_Record_ID"].iloc[0]
        lines = [describe(counterfactuals(ranker, pool, c)) for c in dict.fromkeys(ids + [allocated])]
        examples.append({"request": rid, "allocated": allocated, "lines": lines})

    summary = summarise_misses(ranker, pairs)
    out = Path(paths["outputs"]) / "explain"
    out.mkdir(parents=True, exist_ok=True)
    results = {"examples": examples, "summary": summary}
    (out / "counterfactuals.json").write_text(json.dumps(results, indent=2))

    o, k = summary["outcome"], summary["actionable_kinds"]
    md = ["# Counterfactual explanations", "",
          "What is the smallest realistic change that would make a cornea rank #1?",
          "Actionable: serology confirmed, fewer days in storage. Descriptive: higher ECD,",
          "a grade closer to the request (properties of the tissue, shown to explain only).", "",
          "## Worked examples (held-out test requests)", ""]
    for ex in examples:
        md += [f"### {ex['request']} (allocated: {ex['allocated']})", ""] + [f"- {x}" for x in ex["lines"]] + [""]
    md += ["## Requests where the allocated cornea was not ranked #1", "",
           f"Requests: {summary['requests']}", ""] + [f"- {a}: {b}" for a, b in o.items()]
    md += ["", "Actionable changes that would have been enough:", ""] + [f"- {a}: {b}" for a, b in k.items()]
    if summary["median_days_fewer"] is not None:
        md += ["", f"Median days fewer in storage needed: {summary['median_days_fewer']:.0f}"]
    (out / "counterfactuals.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return results


def run_followup_eda(cfg: dict) -> dict:
    """P1: describe the follow-up cohort (checks, ECD trends, survival, visits, rejection)."""
    from recommendation.data_prep.followup_eda import run

    cohort = Path(cfg["paths"]["followup_cohort"])
    if not cohort.exists():
        raise FileNotFoundError(f"{cohort} not found. Create it first: "
                                "uv run python -m recommendation.main simulate")
    return run(cohort, Path(cfg["paths"]["outputs"]) / "followup_eda")


def run_followup_dataset(cfg: dict) -> dict:
    """P2: 12-month landmark dataset, graft-level split, train-only preprocessing, leakage checks."""
    from recommendation.data_prep.followup_dataset import build

    paths, f = cfg["paths"], cfg["followup"]
    cohort = Path(paths["followup_cohort"])
    if not cohort.exists():
        raise FileNotFoundError(f"{cohort} not found. Create it first: "
                                "uv run python -m recommendation.main simulate")
    return build(cohort, paths["followup_dataset"], Path(paths["models"]) / "followup_preprocessor.json",
                 fractions=tuple(f["split"]), seed=f["seed"])


from recommendation.risk.experiment import COX_CLINICAL, COX_PENALTIES  # noqa: E402  (shared with P5)


def run_followup_baselines(cfg: dict) -> dict:
    """P3: fit every baseline on training grafts; score on validation and repeated CV (test untouched)."""
    from recommendation.data_prep.followup_dataset import load
    from recommendation.evaluation import followup_eval as fe
    from recommendation.risk.cox import CoxPH
    from recommendation.trajectory.baselines import BASELINES

    paths = cfg["paths"]
    table, _ = load(paths["followup_dataset"], Path(paths["models"]) / "followup_preprocessor.json")
    train, val = table[table["split"] == "train"], table[table["split"] == "val"]
    dev = table[table["split"] != "test"]
    source = str(table["data_source"].iloc[0])

    trajectory = {}
    for cls in BASELINES:
        trajectory[cls.name] = {"validation": fe.score_trajectory(cls, train, val),
                                "repeated_cv": fe.cv_trajectory(cls, dev)}

    # Cox penalty chosen by CV on the training grafts only (failure endpoint)
    choice = {}
    for name, feats in (("clinical", COX_CLINICAL), ("all inputs", None)):
        scores = {p: fe.cv_risk(lambda p=p: CoxPH(penalty=p), train, "graft_failure", feats, repeats=2)["c_index"]
                  for p in COX_PENALTIES}
        choice[name] = max(scores, key=scores.get)
    models = {
        "Kaplan-Meier (no inputs)": (fe.KaplanMeierRisk, None),
        f"Cox, clinical inputs (ridge {choice['clinical']})": (lambda: CoxPH(penalty=choice["clinical"]), COX_CLINICAL),
        f"Cox, all inputs (ridge {choice['all inputs']})": (lambda: CoxPH(penalty=choice["all inputs"]), None),
    }
    risk = {}
    for endpoint in fe.ENDPOINTS:
        risk[endpoint] = {name: {"validation": fe.score_risk(f, train, val, endpoint, feats),
                                 "repeated_cv": fe.cv_risk(f, dev, endpoint, feats)}
                          for name, (f, feats) in models.items()}

    res = {"source": source, "train_grafts": int(len(train)), "validation_grafts": int(len(val)),
           "cv_grafts": int(len(dev)), "test_grafts_untouched": int((table["split"] == "test").sum()),
           "trajectory": trajectory, "risk": risk, "cox_penalty_selected": choice,
           "risk_times_after_landmark": list(fe.RISK_TIMES)}
    out = Path(paths["outputs"]) / "followup_baselines"
    out.mkdir(parents=True, exist_ok=True)
    (out / "baselines.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    _write_baselines_md(out / "baselines_summary.md", res)
    return res


def _write_baselines_md(path: Path, r: dict) -> None:
    md = ["# P3 Baselines (post-transplant follow-up)", "",
          f"Data source: {r['source']}. Fitted on {r['train_grafts']} training grafts; scored on "
          f"{r['validation_grafts']} validation grafts and by 5x repeated 5-fold CV over {r['cv_grafts']} "
          f"training + validation grafts. The {r['test_grafts_untouched']} test grafts are not used yet.", "",
          "## Trajectory: ECD at 24 / 36 / 60 months (MAE, cells/mm2; repeated CV)", "",
          "| Model | 24 m | 36 m | 60 m | all | RMSE all |", "|---|---|---|---|---|---|"]
    for name, d in r["trajectory"].items():
        c = d["repeated_cv"]
        md.append(f"| {name} | {c['24m']['mae']:.0f} | {c['36m']['mae']:.0f} | {c['60m']['mae']:.0f} | "
                  f"{c['all']['mae']:.0f} | {c['all']['rmse']:.0f} |")
    for endpoint, models in r["risk"].items():
        md += ["", f"## Risk: {endpoint.replace('_', ' ')} (repeated CV)", "",
               "| Model | C-index | AUC 12 m | AUC 24 m | AUC 36 m | Brier 24 m |", "|---|---|---|---|---|---|"]
        for name, d in models.items():
            c = d["repeated_cv"]
            md.append(f"| {name} | {c['c_index']:.3f} | {c['auc_12m']:.3f} | {c['auc_24m']:.3f} | "
                      f"{c['auc_36m']:.3f} | {c['brier_24m']:.3f} |")
    md += ["", "Times for risk are months after the 12-month visit. AUC is the time-dependent (IPCW) AUC; "
           "Brier is the IPCW Brier score (lower is better). These are the scores P4 and P5 must beat."]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def run_trajectory(cfg: dict, with_curve: bool = True) -> dict:
    """P4: compare trajectory models by repeated CV, learning curve, test the chosen one once, save it."""
    import joblib

    from recommendation.data_prep.followup_dataset import load
    from recommendation.trajectory import experiment

    paths = cfg["paths"]
    table, _ = load(paths["followup_dataset"], Path(paths["models"]) / "followup_preprocessor.json")
    res = experiment.run(table, seed=cfg["followup"]["seed"], with_curve=with_curve)
    res["source"] = str(table["data_source"].iloc[0])

    models = Path(paths["models"])
    models.mkdir(parents=True, exist_ok=True)
    joblib.dump({"name": res["chosen"], "model": res.pop("final_model"), "band": res["band_log_residual_quantiles"],
                 "band_level": res["band_level"], "source": res["source"]}, models / "followup_trajectory.joblib")
    out = Path(paths["outputs"]) / "trajectory"
    out.mkdir(parents=True, exist_ok=True)
    (out / "trajectory_results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    figs = _trajectory_figures(res, out)
    _write_trajectory_md(out / "trajectory_summary.md", res, figs)
    return res


def _trajectory_figures(res: dict, out: Path) -> list:
    from recommendation.data_prep.eda import _figure, _save, _style

    figs = []
    if res["learning_curve"]:
        curve = pd.DataFrame(res["learning_curve"]).groupby(["model", "train_grafts"])["mae_all"].mean().unstack(0)
        fig, ax = _figure(8, 4.2)
        colors = ["#2a78d6", "#eb6834", "#1f9e74", "#8b5cf6", "#c2410c"]
        for c, col in zip(curve.columns, colors):
            ax.plot(curve.index, curve[c], marker="o", linewidth=2, color=col, label=c)
        ax.set_xscale("log")
        ax.set_xticks(curve.index)
        ax.set_xticklabels([str(i) for i in curve.index])
        _style(ax, "Learning curve: ECD prediction error vs training size", "Training grafts (log scale)",
               "MAE, cells/mm²")
        ax.legend(frameon=False, fontsize=8)
        fig.text(0.01, 0.005, f"Data source: {res['source']}", fontsize=7, color="#898781")
        figs.append(_save(fig, out, "learning_curve.png"))
    return figs


def _write_trajectory_md(path: Path, r: dict, figs: list) -> None:
    md = ["# P4 Trajectory models (ECD at 24 / 36 / 60 months)", "", f"Data source: {r['source']}.", "",
          "## Repeated CV (training + validation grafts), MAE in cells/mm2", "",
          "| Model | 24 m | 36 m | 60 m | all | RMSE all |", "|---|---|---|---|---|---|"]
    for name, c in r["cv"].items():
        mark = " **(chosen)**" if name == r["chosen"] else ""
        md.append(f"| {name}{mark} | {c['24m']['mae']:.0f} | {c['36m']['mae']:.0f} | {c['60m']['mae']:.0f} | "
                  f"{c['all']['mae']:.0f} | {c['all']['rmse']:.0f} |")
    md += ["", f"Gradient-boosting settings chosen on training grafts only: {r['tuning']['selected']}.",
           f"Choice rule: lowest CV error; a simpler model within {int(r['tie_margin'] * 100)}% wins.", "",
           "## Test grafts (used once)", "", "| Model | 24 m | 36 m | 60 m | all |", "|---|---|---|---|---|"]
    for name, d in r["test"].items():
        e = d["errors"]
        md.append(f"| {name} | {e['24m']['mae']:.0f} | {e['36m']['mae']:.0f} | {e['60m']['mae']:.0f} | {e['all']['mae']:.0f} |")
    cov = r["test"][r["chosen"]].get("band_coverage", {})
    md += ["", f"{r['band_level']} prediction band coverage on test: " + ", ".join(
        f"{h} {d['coverage']:.0%} (n={d['n']})" for h, d in cov.items())]
    if r["learning_curve"]:
        curve = pd.DataFrame(r["learning_curve"]).groupby(["train_grafts", "model"])["mae_all"].mean().unstack()
        md += ["", "## Learning curve (separate simulated cohort; MAE all horizons)", "",
               "| Training grafts | " + " | ".join(curve.columns) + " |", "|---" * (len(curve.columns) + 1) + "|"]
        md += [f"| {n} | " + " | ".join(f"{v:.0f}" for v in row) + " |" for n, row in curve.iterrows()]
    md += ["", "Figures: " + ", ".join(figs)]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def run_risk(cfg: dict) -> dict:
    """P5: compare risk models (Cox, gradient-boosted Cox, DeepSurv) per endpoint, test once, save."""
    import joblib

    from recommendation.data_prep.followup_dataset import load
    from recommendation.risk import experiment

    paths = cfg["paths"]
    table, _ = load(paths["followup_dataset"], Path(paths["models"]) / "followup_preprocessor.json")
    res = experiment.run(table, seed=cfg["followup"]["seed"])
    res["source"] = str(table["data_source"].iloc[0])
    finals = res.pop("final_models")

    models = Path(paths["models"])
    models.mkdir(parents=True, exist_ok=True)
    joblib.dump({"source": res["source"], "models": finals}, models / "followup_risk.joblib")
    out = Path(paths["outputs"]) / "risk"
    out.mkdir(parents=True, exist_ok=True)
    (out / "risk_results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    figs = [_calibration_figure(res, out)]
    _write_risk_md(out / "risk_summary.md", res, figs)
    return res


def _calibration_figure(res: dict, out: Path) -> str:
    import matplotlib.pyplot as plt

    from recommendation.data_prep.eda import SURFACE, _save, _style

    eps = res["endpoints"]
    fig, axes = plt.subplots(1, len(eps), figsize=(10, 4), facecolor=SURFACE)
    for ax, (endpoint, r) in zip(axes, eps.items()):
        cal = pd.DataFrame(r["calibration_24m"])
        top = max(cal["predicted_risk"].max(), cal["observed_risk"].max(), 0.05) * 1.1
        ax.plot([0, top], [0, top], color="#c3c2b7", linewidth=1, linestyle="--")
        ax.plot(cal["predicted_risk"], cal["observed_risk"], marker="o", color="#2a78d6", linewidth=2)
        _style(ax, f"{endpoint.replace('_', ' ').capitalize()}: {r['chosen']}", "Predicted 24-month risk",
               "Observed (Kaplan-Meier)")
        ax.yaxis.set_major_locator(plt.MaxNLocator(5))
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
    fig.text(0.01, 0.005, f"Data source: {res['source']}; out-of-fold predictions, 5 risk groups",
             fontsize=7, color="#898781")
    return _save(fig, out, "calibration_24m.png")


def _write_risk_md(path: Path, r: dict, figs: list) -> None:
    md = ["# P5 Risk models (after the 12-month visit)", "", f"Data source: {r['source']}.", "",
          f"Settings chosen on training grafts only: {r['settings']}.",
          f"Choice rule: highest CV C-index; a simpler model within {r['tie_margin']} wins.", ""]
    for endpoint, e in r["endpoints"].items():
        md += [f"## {endpoint.replace('_', ' ').capitalize()}", "", "Repeated CV (training + validation grafts):", "",
               "| Model | C-index | AUC 12 m | AUC 24 m | AUC 36 m | Brier 24 m |", "|---|---|---|---|---|---|"]
        for name, c in e["cv"].items():
            mark = " **(chosen)**" if name == e["chosen"] else ""
            md.append(f"| {name}{mark} | {c['c_index']:.3f} | {c['auc_12m']:.3f} | {c['auc_24m']:.3f} | "
                      f"{c['auc_36m']:.3f} | {c['brier_24m']:.3f} |")
        md += ["", "Test grafts (used once):", "", "| Model | events | C-index | AUC 24 m | Brier 24 m |",
               "|---|---|---|---|---|"]
        for name, c in e["test"].items():
            md.append(f"| {name} | {c['events']} | {c['c_index']:.3f} | {c['auc_24m']:.3f} | {c['brier_24m']:.3f} |")
        md += ["", "Calibration at 24 months (out-of-fold):", "", "| Group | n | predicted | observed |", "|---|---|---|---|"]
        md += [f"| {c['group']} | {c['n']} | {c['predicted_risk']:.3f} | {c['observed_risk']:.3f} |"
               for c in e["calibration_24m"]]
        md.append("")
    md += ["Times are months after the 12-month visit. Figures: " + ", ".join(figs)]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def run_followup_explain(cfg: dict) -> dict:
    """P6: SHAP reasons and descriptive counterfactuals for the chosen trajectory and risk models."""
    import joblib

    from recommendation.data_prep.followup_dataset import load
    from recommendation.explain import followup_explain

    paths = cfg["paths"]
    models = Path(paths["models"])
    table, _ = load(paths["followup_dataset"], models / "followup_preprocessor.json")
    res = followup_explain.run(table, joblib.load(models / "followup_trajectory.joblib"),
                               joblib.load(models / "followup_risk.joblib"))
    res["source"] = str(table["data_source"].iloc[0])
    out = Path(paths["outputs"]) / "followup_explain"
    out.mkdir(parents=True, exist_ok=True)
    (out / "followup_explanations.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    figs = [_followup_importance_figure(res, out)]
    _write_followup_explain_md(out / "followup_explain_summary.md", res, figs)
    return res


def _followup_importance_figure(res: dict, out: Path) -> str:
    import matplotlib.pyplot as plt

    from recommendation.data_prep.eda import SURFACE, _save, _style

    imp = res["global_importance"]
    fig, axes = plt.subplots(1, len(imp), figsize=(12, 3.8), facecolor=SURFACE)
    for ax, (name, vals) in zip(axes, imp.items()):
        s = pd.Series(vals).sort_values()
        s = s[s > 0]
        ax.barh(s.index, s.values / s.sum() * 100, color="#2a78d6")
        _style(ax, name.replace("_", " "), "share of explanation (%)")
        ax.grid(axis="x", color="#e1e0d9")
    fig.text(0.01, 0.005, f"Data source: {res['source']}; mean |SHAP| per reason", fontsize=7, color="#898781")
    return _save(fig, out, "followup_reason_importance.png")


def _write_followup_explain_md(path: Path, r: dict, figs: list) -> None:
    md = ["# P6 Explanations (post-transplant models)", "", f"Data source: {r['source']}. Trajectory model: "
          f"{r['trajectory_model']}; risk models: {r['risk_models']}.", "",
          "## Sanity checks", "", "| Check | Result | Detail |", "|---|---|---|"]
    md += [f"| {c['check']} | {'pass' if c['ok'] else '**FAIL**'} | {c['detail']} |" for c in r["checks"]]
    md += ["", "## What drives the predictions (share of mean |SHAP|)", ""]
    for name, vals in r["global_importance"].items():
        s = pd.Series(vals)
        s = (s / s.sum() * 100).sort_values(ascending=False)
        md.append(f"- **{name.replace('_', ' ')}**: " + ", ".join(f"{k} {v:.0f}%" for k, v in s.items() if v >= 1))
    md += ["", "## Example test grafts", ""]
    for e in r["examples"]:
        md += [f"### {e['graft']} ({e['procedure']}, 12-month ECD {e['ECD_12m']:.0f})", "",
               f"- Predicted 60-month ECD {e['predicted_ECD_60m']}: {e['why_trajectory']}"]
        if e["trajectory_counterfactual"]:
            md.append(f"  - {e['trajectory_counterfactual']}")
        for ep in ("graft_failure", "low_ecd"):
            d = e[ep]
            if "note" in d:
                md.append(f"- {ep.replace('_', ' ')}: {d['note']}")
                continue
            md.append(f"- {ep.replace('_', ' ')} risk by 24 months after the 12-month visit {d['risk_24m']:.0%}: {d['why']}")
            if d["counterfactual"]:
                md.append(f"  - {d['counterfactual']}")
        md.append("")
    md += ["Counterfactuals are descriptive (they explain the model); the 12-month ECD is a measurement, "
           "not a treatment choice. Risk percentages come from a model whose calibration is not yet "
           "corrected (see P5).", "", "Figures: " + ", ".join(figs)]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def run_followup(cfg: dict):
    raise NotImplementedError("Needs trajectory/risk outputs and clinician follow-up decisions.")
