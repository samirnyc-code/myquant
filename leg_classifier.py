"""
leg_classifier.py — Stage 1 logistic maturity scorer for ES leg classification.

Implements the L1-regularised logistic classifier described in spec §6.3.

The binary target is `is_terminal_pb_leg`:
  1 → PB_L2 or PB_L3 (terminal pullback leg — the expensive false-positive)
  0 → IMPULSE_L1, IMPULSE_LN (continuation context)

PB_L1 and REVERSAL are excluded from the binary target by default (edge
is ambiguous; add them back with target_states/negative_states overrides).

Primary entry points
--------------------
train(feature_df, gt_labels, ...) -> ClassifierResult
    Fit and walk-forward validate the logistic scorer.

score(feature_df, model) -> pd.DataFrame
    Score new (unlabeled) legs with calibrated P(terminal_pb_leg).

to_rule_set(model) -> list[dict]
    Extract the L1-sparse decision rule for NinjaScript porting (spec §10.2).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import expit as sigmoid
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

from leg_features import FEATURE_COLS
from leg_label_store import LEG_STATES, load_ground_truth

# ── Target definition ─────────────────────────────────────────────────────────

POSITIVE_STATES  = {"PB_L2", "PB_L3"}          # terminal PB legs
NEGATIVE_STATES  = {"IMPULSE_L1", "IMPULSE_LN"} # genuine impulse legs
EXCLUDE_STATES   = {"PB_L1", "REVERSAL", "UNLABELED"}  # excluded from binary target

C_DEFAULT    = 0.1     # L1 regularisation strength (lower = more sparse)
MAX_ITER     = 2000


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class ClassifierResult:
    """Trained logistic scorer + walk-forward evaluation results."""
    model:        LogisticRegression
    scaler:       StandardScaler
    feature_cols: list[str]         # columns that survived L1 (non-zero coeff)
    all_cols:     list[str]         # all input columns (before L1 pruning)

    # Walk-forward evaluation
    wf_folds:     list[dict] = field(default_factory=list)
    wf_brier:     float = np.nan
    wf_logloss:   float = np.nan
    wf_precision: float = np.nan
    wf_recall:    float = np.nan
    wf_f1:        float = np.nan

    # Full-sample fit metrics
    full_brier:   float = np.nan
    full_logloss: float = np.nan

    @property
    def coeff_table(self) -> pd.DataFrame:
        """Non-zero feature coefficients sorted by absolute magnitude."""
        if not hasattr(self.model, "coef_"):
            return pd.DataFrame()
        coefs = self.model.coef_[0]
        cols  = self.all_cols
        rows  = [(c, float(w)) for c, w in zip(cols, coefs) if w != 0]
        df    = pd.DataFrame(rows, columns=["feature", "coeff"])
        df["abs_coeff"] = df["coeff"].abs()
        return df.sort_values("abs_coeff", ascending=False).reset_index(drop=True)

    def summary(self) -> str:
        lines = [
            "=== Logistic Maturity Scorer ===",
            f"Walk-forward Brier:      {self.wf_brier:.4f}",
            f"Walk-forward LogLoss:    {self.wf_logloss:.4f}",
            f"Walk-forward Precision:  {self.wf_precision:.3f}",
            f"Walk-forward Recall:     {self.wf_recall:.3f}",
            f"Walk-forward F1:         {self.wf_f1:.3f}",
            f"Non-zero features (L1):  {len(self.feature_cols)} / {len(self.all_cols)}",
        ]
        return "\n".join(lines)


# ── Data prep ─────────────────────────────────────────────────────────────────

def _build_dataset(
    feature_df: pd.DataFrame,
    gt_labels: pd.DataFrame,
    positive_states: set[str] = POSITIVE_STATES,
    negative_states: set[str] = NEGATIVE_STATES,
    feature_cols: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str], pd.DatetimeIndex]:
    """
    Join features with labels, filter to binary-target rows, impute NaN.

    Returns (X, y, used_cols, start_dt_index)
    """
    if feature_cols is None:
        feature_cols = [c for c in FEATURE_COLS if c in feature_df.columns]

    # Join on leg_id (index of feature_df)
    gt = gt_labels[gt_labels["leg_state"].isin(positive_states | negative_states)].copy()
    gt["leg_id"] = gt["leg_id"].astype(int)

    merged = feature_df.reset_index().rename(columns={"index": "leg_id"})
    if "leg_id" not in merged.columns and feature_df.index.name == "leg_id":
        merged = feature_df.reset_index()

    merged = merged.merge(
        gt[["leg_id", "leg_state", "start_dt"]],
        on="leg_id",
        how="inner",
    )

    if merged.empty:
        raise ValueError("No labeled legs found after join. Label some legs first.")

    merged = merged.sort_values("start_dt")
    y_raw  = merged["leg_state"].isin(positive_states).astype(int).to_numpy()

    X_df = merged[feature_cols].copy()
    # Median imputation for NaN (only valid at training time — store medians)
    medians = X_df.median()
    X_df    = X_df.fillna(medians)
    X       = X_df.to_numpy(dtype=np.float64)

    start_dts = pd.to_datetime(merged["start_dt"])
    return X, y_raw, feature_cols, start_dts


# ── Walk-forward validation ───────────────────────────────────────────────────

def _walk_forward(
    X: np.ndarray,
    y: np.ndarray,
    start_dts: pd.DatetimeIndex,
    train_months: int = 18,
    test_months:  int = 3,
    C: float = C_DEFAULT,
) -> list[dict]:
    """
    Walk-forward validation (spec §8.3). Purely chronological train/test splits.
    Returns list of per-fold result dicts.
    """
    start_dts = pd.DatetimeIndex(start_dts)
    min_dt    = start_dts.min()
    max_dt    = start_dts.max()
    folds     = []

    fold_start = min_dt
    while True:
        train_end = fold_start + pd.DateOffset(months=train_months)
        test_end  = train_end  + pd.DateOffset(months=test_months)
        if train_end >= max_dt:
            break

        train_mask = start_dts < train_end
        test_mask  = (start_dts >= train_end) & (start_dts < test_end)

        if train_mask.sum() < 30 or test_mask.sum() < 5:
            fold_start += pd.DateOffset(months=test_months)
            continue

        X_tr, y_tr = X[train_mask], y[train_mask]
        X_te, y_te = X[test_mask],  y[test_mask]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        clf = LogisticRegression(
            penalty="l1", solver="liblinear", C=C,
            max_iter=MAX_ITER, class_weight="balanced",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clf.fit(X_tr_s, y_tr)

        p_te  = clf.predict_proba(X_te_s)[:, 1]
        y_hat = (p_te >= 0.5).astype(int)

        pr, rc, f1, _ = precision_recall_fscore_support(
            y_te, y_hat, average="binary", zero_division=0
        )
        folds.append({
            "train_start": str(fold_start.date()),
            "train_end":   str(train_end.date()),
            "test_start":  str(train_end.date()),
            "test_end":    str(test_end.date()),
            "n_train":     int(train_mask.sum()),
            "n_test":      int(test_mask.sum()),
            "brier":       float(brier_score_loss(y_te, p_te)),
            "logloss":     float(log_loss(y_te, p_te)),
            "precision":   float(pr),
            "recall":      float(rc),
            "f1":          float(f1),
            "pos_rate_te": float(y_te.mean()),
        })
        fold_start += pd.DateOffset(months=test_months)

    return folds


# ── Train ─────────────────────────────────────────────────────────────────────

def train(
    feature_df: pd.DataFrame,
    gt_labels: pd.DataFrame | None = None,
    positive_states: set[str] = POSITIVE_STATES,
    negative_states: set[str] = NEGATIVE_STATES,
    C: float = C_DEFAULT,
    train_months: int = 18,
    test_months:  int = 3,
    feature_cols: list[str] | None = None,
) -> ClassifierResult:
    """
    Fit L1 logistic scorer and run walk-forward validation.

    Parameters
    ----------
    feature_df      : output of leg_features.build_feature_matrix() (index = leg_id)
    gt_labels       : ground-truth label DataFrame (from leg_label_store). If None,
                      loads from the default store file.
    positive_states : label states that map to y=1 (terminal PB legs)
    negative_states : label states that map to y=0 (impulse legs)
    C               : L1 regularisation (lower = sparser feature set)
    train_months    : walk-forward training window length
    test_months     : walk-forward test window length
    feature_cols    : subset of features to use. None = all FEATURE_COLS present.

    Returns
    -------
    ClassifierResult with fitted model + walk-forward evaluation.
    """
    if gt_labels is None:
        gt_labels = load_ground_truth()

    X, y, used_cols, start_dts = _build_dataset(
        feature_df, gt_labels,
        positive_states=positive_states,
        negative_states=negative_states,
        feature_cols=feature_cols,
    )

    if len(np.unique(y)) < 2:
        raise ValueError("Only one class in labeled data. Need both positive and negative examples.")

    # Walk-forward
    wf_folds = _walk_forward(X, y, start_dts, train_months, test_months, C)

    # Full-sample fit (for NinjaScript export)
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    clf      = LogisticRegression(
        penalty="l1", solver="liblinear", C=C,
        max_iter=MAX_ITER, class_weight="balanced",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf.fit(X_scaled, y)

    p_full = clf.predict_proba(X_scaled)[:, 1]
    full_brier   = float(brier_score_loss(y, p_full))
    full_logloss = float(log_loss(y, p_full))

    # Surviving features (non-zero L1 coeff)
    nonzero_mask   = clf.coef_[0] != 0
    surviving_cols = [c for c, nz in zip(used_cols, nonzero_mask) if nz]

    # Aggregate WF metrics
    if wf_folds:
        wf_brier     = float(np.mean([f["brier"]     for f in wf_folds]))
        wf_logloss   = float(np.mean([f["logloss"]   for f in wf_folds]))
        wf_precision = float(np.mean([f["precision"] for f in wf_folds]))
        wf_recall    = float(np.mean([f["recall"]    for f in wf_folds]))
        wf_f1        = float(np.mean([f["f1"]        for f in wf_folds]))
    else:
        wf_brier = wf_logloss = wf_precision = wf_recall = wf_f1 = np.nan

    return ClassifierResult(
        model=clf,
        scaler=scaler,
        feature_cols=surviving_cols,
        all_cols=used_cols,
        wf_folds=wf_folds,
        wf_brier=wf_brier,
        wf_logloss=wf_logloss,
        wf_precision=wf_precision,
        wf_recall=wf_recall,
        wf_f1=wf_f1,
        full_brier=full_brier,
        full_logloss=full_logloss,
    )


# ── Score ─────────────────────────────────────────────────────────────────────

def score(
    feature_df: pd.DataFrame,
    result: ClassifierResult,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """
    Score legs with P(terminal_pb_leg).

    Parameters
    ----------
    feature_df : output of leg_features.build_feature_matrix()
    result     : trained ClassifierResult
    threshold  : probability cutoff for binary prediction

    Returns
    -------
    DataFrame with columns:
        leg_id, p_terminal_pb, is_terminal_pb (binary), direction,
        start_dt, end_dt, start_price, end_price
    """
    cols = result.all_cols
    X_df = feature_df.reset_index().copy()
    leg_ids = X_df["leg_id"].astype(int).tolist() if "leg_id" in X_df.columns else X_df.index.tolist()

    X_raw = X_df[[c for c in cols if c in X_df.columns]].copy()
    # Fill missing cols with 0
    for c in cols:
        if c not in X_raw.columns:
            X_raw[c] = 0.0
    X_raw = X_raw[cols].fillna(X_raw[cols].median())

    X_scaled = result.scaler.transform(X_raw.to_numpy(dtype=np.float64))
    probs    = result.model.predict_proba(X_scaled)[:, 1]

    out = pd.DataFrame({
        "leg_id":          leg_ids,
        "p_terminal_pb":   probs,
        "is_terminal_pb":  (probs >= threshold).astype(int),
    })

    # Attach identity columns if present
    for col in ["direction", "start_dt", "end_dt", "start_price", "end_price"]:
        if col in X_df.columns:
            out[col] = X_df[col].values

    return out.set_index("leg_id")


# ── NinjaScript rule export ───────────────────────────────────────────────────

def to_rule_set(result: ClassifierResult) -> list[dict]:
    """
    Extract the L1-sparse rule set for NinjaScript porting (spec §10.2).

    The logistic decision boundary is:
        P = sigmoid(w1*f1 + w2*f2 + ... + b)

    Features are in StandardScaler-normalised space:
        f_scaled = (f_raw - mean) / std

    To apply in NinjaScript without the scaler:
        w_raw_i = w_scaled_i / std_i
        adjusted_bias = b + sum(w_scaled_i * (-mean_i / std_i))

    Returns a list of dicts with:
        feature, raw_coeff, raw_mean, raw_std
        (NinjaScript: P = sigmoid(sum(raw_coeff_i * (feat_i - raw_mean_i) / raw_std_i) + bias))
    """
    if not hasattr(result.model, "coef_"):
        return []

    coefs    = result.model.coef_[0]
    bias     = float(result.model.intercept_[0])
    means    = result.scaler.mean_
    stds     = result.scaler.scale_
    cols     = result.all_cols

    rules = []
    for i, (col, w) in enumerate(zip(cols, coefs)):
        if w == 0:
            continue
        rules.append({
            "feature":   col,
            "coeff_scaled": float(w),
            "mean":      float(means[i]),
            "std":       float(stds[i]),
            "coeff_raw": float(w / stds[i]) if stds[i] > 0 else 0.0,
        })

    rules.append({
        "feature":     "__bias__",
        "coeff_scaled": bias,
        "mean":        0.0,
        "std":         1.0,
        "coeff_raw":   bias,
    })
    return rules


def rules_to_ninjascript_comment(rules: list[dict]) -> str:
    """
    Format the rule set as a NinjaScript code comment block.
    Paste this into the NT8 indicator for the logistic scorer calculation.
    """
    lines = [
        "// === Leg Classifier — Logistic Scorer (auto-generated) ===",
        "// P_terminal_pb = sigmoid(score)",
        "// double score = 0;",
    ]
    for r in rules:
        if r["feature"] == "__bias__":
            lines.append(f"// score += {r['coeff_raw']:.6f}; // bias")
        else:
            mean = r["mean"]
            std  = r["std"]
            craw = r["coeff_raw"]
            lines.append(
                f"// score += {craw:.6f} * ({r['feature']} - {mean:.6f}) "
                f"/ {std:.6f};  // w={r['coeff_scaled']:.4f}"
            )
    lines.append("// double p = 1.0 / (1.0 + Math.Exp(-score));")
    return "\n".join(lines)
