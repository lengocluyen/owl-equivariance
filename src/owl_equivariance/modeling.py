"""Regression analysis of the exported long-format table (spec section 25.2).

The per-condition tables answer "how large is the gap". They cannot answer the question a
reviewer will actually ask -- *does the gap survive controlling for tokenization and context
length* -- because that needs the covariates in a model that respects the clustering.

Two estimators are offered, because they answer subtly different questions and the honest
thing is to say which one produced a number:

``gee`` (default)
    Population-averaged logistic regression with an exchangeable working correlation and
    cluster-robust standard errors, clustered on the base item. This is what the paired
    design implies: the nine orbit members of one base item are repeated measures of the
    same problem. Numerically robust, and the standard errors do not depend on the working
    correlation being right.

``bayes_mixed``
    Bayesian binomial mixed GLM with an explicit random intercept per base item.  With at
    least five ontologies it also includes an ontology random intercept.  This is an
    immediately executable Python check of the crossed-intercept specification, but it is
    a variational approximation; the v3.3 primary confirmatory fit uses ``lme4::glmer``.

An ontology variance component cannot be estimated from one or two levels.  ``auto`` uses
an ontology random intercept for ``bayes_mixed`` with at least five levels, a fixed effect
for multi-ontology GEE/small panels, and no ontology term for a single source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from .metrics.stats import holm_correction

DEFAULT_TERMS = [
    "condition",
    "task_type",
    "proof_depth",
    "context_axioms",
    "token_delta",
]


@dataclass
class ModelResult:
    estimator: str
    outcome: str
    formula: str
    n_observations: int
    n_groups: int
    group_var: str
    terms: list[str]
    n_ontologies: int = 0
    ontology_effect: str = "none"
    random_effects: list[str] = field(default_factory=list)
    fit_status: str = "FIT"
    condition_model_interaction: bool = False
    summary_text: str = ""
    coefficients: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "estimator": self.estimator,
            "outcome": self.outcome,
            "formula": self.formula,
            "n_observations": self.n_observations,
            "n_groups": self.n_groups,
            "group_var": self.group_var,
            "terms": self.terms,
            "n_ontologies": self.n_ontologies,
            "ontology_effect": self.ontology_effect,
            "random_effects": self.random_effects,
            "fit_status": self.fit_status,
            "condition_model_interaction": self.condition_model_interaction,
            "coefficients": self.coefficients,
            "notes": self.notes,
        }


def _require(module: str):
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            f"{module} is required for regression analysis; "
            "install with: pip install 'owl-equivariance[stats]'"
        ) from exc


def fit(
    csv_path: str,
    estimator: str = "gee",
    reference: str = "C0",
    terms: list[str] | None = None,
    model_filter: str | None = None,
    outcome: str = "correct",
    condition_model_interaction: bool = False,
    ontology_effect: str = "auto",
) -> ModelResult:
    """Fit the condition effect with covariates and explicit dependence structure."""
    pd = _require("pandas")
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    frame = pd.read_csv(csv_path)
    notes: list[str] = []
    if outcome not in {"correct", "parsed"}:
        raise ValueError("outcome must be 'correct' or 'parsed'")
    if outcome not in frame.columns:
        raise ValueError(f"outcome {outcome!r} is absent from {csv_path}")
    for required in ("base_item_id", "ontology_id", "model", "condition"):
        if required not in frame.columns:
            raise ValueError(f"required column {required!r} is absent from {csv_path}")

    if model_filter:
        frame = frame[frame["model"] == model_filter].copy()
    elif frame["model"].nunique() > 1:
        # Pooling models without a model term would average away exactly the between-model
        # variation the pilot is meant to report.
        notes.append(
            f"{frame['model'].nunique()} models pooled; add --model to fit one at a time, "
            "or read the model term as a fixed effect"
        )

    chosen = list(terms or DEFAULT_TERMS)

    # Drop covariates that are constant or entirely missing: statsmodels would either fail
    # or silently return a meaningless coefficient.
    usable: list[str] = []
    # Formula terms are not necessarily dataframe column names.  In particular,
    # ``condition:C(model)`` is a Patsy interaction expression.  Keep the source
    # columns needed for complete-case filtering separate from the terms passed to
    # statsmodels; otherwise pandas.dropna() tries to find a literal interaction
    # column and the pooled publication model crashes after inference has finished.
    required_columns = {outcome, "base_item_id"}
    for term in chosen:
        if term == "condition":
            usable.append(term)
            required_columns.add(term)
            continue
        if term == "task_type":
            if term not in frame.columns or frame[term].dropna().nunique() < 2:
                notes.append("covariate 'task_type' has fewer than two levels; dropped")
            else:
                usable.append("C(task_type)")
                required_columns.add(term)
            continue
        if term not in frame.columns:
            notes.append(f"covariate {term!r} absent from the table; dropped")
            continue
        column = pd.to_numeric(frame[term], errors="coerce")
        if column.notna().sum() == 0:
            notes.append(f"covariate {term!r} is entirely missing; dropped")
            continue
        if column.nunique(dropna=True) < 2:
            notes.append(f"covariate {term!r} is constant; dropped")
            continue
        # A covariate that is constant inside every condition is just another encoding of
        # the condition factor. Keeping both makes the condition effect unidentified (the
        # common symptom is a NaN robust standard error/p-value).
        within_condition_levels = (
            frame.assign(_candidate=column)
            .groupby("condition", observed=False)["_candidate"]
            .nunique(dropna=True)
        )
        if not within_condition_levels.empty and within_condition_levels.max() <= 1:
            notes.append(
                f"covariate {term!r} has no within-condition variation and is collinear "
                "with condition; dropped"
            )
            continue
        frame[term] = column
        usable.append(term)
        required_columns.add(term)

    n_ontologies = int(frame["ontology_id"].nunique())
    resolved_ontology_effect = _resolve_ontology_effect(
        estimator, ontology_effect, n_ontologies
    )
    random_effect_terms = []
    if estimator == "bayes_mixed":
        random_effect_terms.append("ontology_id:base_item_id")
        if resolved_ontology_effect == "random":
            random_effect_terms.insert(0, "ontology_id")
    if resolved_ontology_effect == "fixed":
        usable.append("C(ontology_id)")
        required_columns.add("ontology_id")
        notes.append(f"ontology entered as a fixed effect ({n_ontologies} levels)")
    elif resolved_ontology_effect == "random":
        required_columns.add("ontology_id")
        notes.append(
            f"ontology entered as a random intercept ({n_ontologies} levels)"
        )
    elif n_ontologies == 1:
        notes.append("one ontology: no ontology term, and no cross-ontology claim is supported")
    else:
        notes.append("ontology effect explicitly omitted")

    if frame["model"].nunique() > 1 and not model_filter:
        usable.append("C(model)")
        required_columns.add("model")
        if condition_model_interaction:
            usable.append("condition:C(model)")
            notes.append("condition-by-model interaction included")
    elif condition_model_interaction:
        notes.append(
            "condition-by-model interaction requested but fewer than two models remain; "
            "interaction omitted"
        )

    frame = frame.dropna(subset=sorted(required_columns))
    # A base-item id is only meaningful inside its ontology.  The panel freeze rejects
    # cross-source collisions, but the composite cluster keeps ad-hoc analyses correct too.
    frame["_item_cluster"] = (
        frame["ontology_id"].astype(str) + "::" + frame["base_item_id"].astype(str)
    )

    # C0 must be the reference level or the condition coefficients answer a different
    # question than the tables do.
    levels = [reference] + sorted(set(frame["condition"]) - {reference})
    frame["condition"] = pd.Categorical(frame["condition"], categories=levels)

    formula = outcome + " ~ " + " + ".join(usable)
    groups = frame["_item_cluster"]
    if frame[outcome].nunique(dropna=True) < 2:
        notes.append(
            f"outcome {outcome!r} is constant; no logistic model is identifiable"
        )
        return ModelResult(
            estimator=estimator,
            outcome=outcome,
            formula=formula,
            n_observations=int(len(frame)),
            n_groups=int(groups.nunique()),
            group_var="ontology_id:base_item_id",
            terms=usable,
            n_ontologies=n_ontologies,
            ontology_effect=resolved_ontology_effect,
            random_effects=random_effect_terms,
            fit_status="CONSTANT_OUTCOME",
            condition_model_interaction=condition_model_interaction,
            summary_text=(
                f"No fit: outcome {outcome!r} has one observed level "
                f"({frame[outcome].iloc[0] if len(frame) else 'none'})."
            ),
            coefficients=[],
            notes=notes,
        )

    if estimator == "gee":
        model = smf.gee(
            formula,
            groups="_item_cluster",
            data=frame,
            family=sm.families.Binomial(),
            cov_struct=sm.cov_struct.Exchangeable(),
        )
        fitted = model.fit()
        summary_text = str(fitted.summary())
        finite_fit = all(isfinite(float(value)) for value in fitted.params) and all(
            isfinite(float(value)) for value in fitted.bse
        )
        if finite_fit:
            coefficients = _coefficients(fitted, pd)
            fit_status = "FIT"
            notes.append(
                "p_value_holm adjusts the family of condition-vs-reference coefficients; "
                "the statsmodels text summary shows raw p-values"
            )
        else:
            coefficients = []
            fit_status = "NON_IDENTIFIABLE"
            events = int(frame[outcome].astype(bool).sum())
            notes.append(
                "the fitted covariance or coefficients were non-finite; the logistic GEE "
                f"is non-identifiable for this sparse outcome ({events} events and "
                f"{len(frame) - events} non-events). Report descriptive validity rates "
                "instead of inferential coefficients"
            )
    elif estimator == "bayes_mixed":
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

        variance_components = {"base_item": "0 + C(_item_cluster)"}
        if resolved_ontology_effect == "random":
            variance_components["ontology"] = "0 + C(ontology_id)"
        model = BinomialBayesMixedGLM.from_formula(
            formula, variance_components, frame
        )
        fitted = model.fit_vb()
        summary_text = str(fitted.summary())
        coefficients = _bayes_coefficients(model, fitted)
        fit_status = "FIT_APPROXIMATE"
        notes.append(
            "variational Bayesian approximation: fixed-effect intervals and p-values are "
            "approximate; use the preregistered lme4 Laplace GLMM for primary inference"
        )
    else:
        raise ValueError(f"unknown estimator {estimator!r}; expected 'gee' or 'bayes_mixed'")

    return ModelResult(
        estimator=estimator,
        outcome=outcome,
        formula=formula,
        n_observations=int(len(frame)),
        n_groups=int(groups.nunique()),
        group_var="ontology_id:base_item_id",
        terms=usable,
        n_ontologies=n_ontologies,
        ontology_effect=resolved_ontology_effect,
        random_effects=random_effect_terms,
        fit_status=fit_status,
        condition_model_interaction=condition_model_interaction,
        summary_text=summary_text,
        coefficients=coefficients,
        notes=notes,
    )


def _resolve_ontology_effect(estimator: str, requested: str, levels: int) -> str:
    if requested not in {"auto", "fixed", "random", "none"}:
        raise ValueError("ontology_effect must be auto, fixed, random, or none")
    if requested == "random":
        if estimator != "bayes_mixed":
            raise ValueError("ontology_effect='random' requires estimator='bayes_mixed'")
        if levels < 5:
            raise ValueError(
                f"ontology random intercept requires at least five levels, found {levels}"
            )
        return "random"
    if requested == "fixed":
        if levels < 2:
            raise ValueError("ontology fixed effect requires at least two levels")
        return "fixed"
    if requested == "none":
        return "none"
    if estimator == "bayes_mixed" and levels >= 5:
        return "random"
    return "fixed" if levels > 1 else "none"


def _coefficients(fitted, pd) -> list[dict]:
    import numpy as np

    conf = fitted.conf_int()
    out = []
    for name in fitted.params.index:
        coefficient = float(fitted.params[name])
        out.append(
            {
                "term": name,
                "coefficient": coefficient,
                "odds_ratio": float(np.exp(coefficient)),
                "std_error": float(fitted.bse[name]),
                "z": float(fitted.tvalues[name]),
                "p_value": float(fitted.pvalues[name]),
                "p_value_holm": None,
                "ci_low": float(conf.loc[name, 0]),
                "ci_high": float(conf.loc[name, 1]),
            }
        )
    condition_rows = [
        row
        for row in out
        if row["term"].startswith("condition[") and isfinite(row["p_value"])
    ]
    if condition_rows:
        adjusted = holm_correction(
            {row["term"]: row["p_value"] for row in condition_rows}
        )
        for row in condition_rows:
            row["p_value_holm"] = adjusted[row["term"]]
    return out


def _bayes_coefficients(model, fitted) -> list[dict]:
    """Approximate fixed-effect table for the variational Bayesian sensitivity fit."""
    import numpy as np
    from math import erfc, sqrt

    out = []
    for name, coefficient, std_error in zip(
        model.exog_names, fitted.fe_mean, fitted.fe_sd
    ):
        coefficient = float(coefficient)
        std_error = float(std_error)
        z = coefficient / std_error if std_error > 0 else float("nan")
        p_value = erfc(abs(z) / sqrt(2.0)) if isfinite(z) else float("nan")
        out.append(
            {
                "term": name,
                "coefficient": coefficient,
                "odds_ratio": float(np.exp(coefficient)),
                "std_error": std_error,
                "z": z,
                "p_value": p_value,
                "p_value_holm": None,
                "ci_low": coefficient - 1.96 * std_error,
                "ci_high": coefficient + 1.96 * std_error,
            }
        )
    condition_rows = [
        row
        for row in out
        if row["term"].startswith("condition[") and isfinite(row["p_value"])
    ]
    if condition_rows:
        adjusted = holm_correction(
            {row["term"]: row["p_value"] for row in condition_rows}
        )
        for row in condition_rows:
            row["p_value_holm"] = adjusted[row["term"]]
    return out


COEFFICIENT_COLUMNS = [
    "term",
    "coefficient",
    "odds_ratio",
    "std_error",
    "z",
    "p_value",
    "p_value_holm",
    "ci_low",
    "ci_high",
]
