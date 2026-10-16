"""End-to-end pipelines for the recommendation module.

Implemented:
    run_matching   build matching dataset -> MCDA ranking -> evaluation
    run_ranker     train the ML ranker on the same split and compare it with MCDA
    run_explain    SHAP explanations for the trained ranker (global + "Why #1?")
    run_analysis   ablation, learning curve, subgroup and error analysis of the ranker
    run_counterfactual  "what would make this cornea #1?" for examples and all missed requests

Planned (need recipient follow-up data from NEBSL):
    run_trajectory, run_risk, run_followup
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


def run_trajectory(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits (ECD/CV/HEX over time).")


def run_risk(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits and the low-ECD endpoint definition.")


def run_followup(cfg: dict):
    raise NotImplementedError("Needs trajectory/risk outputs and clinician follow-up decisions.")
