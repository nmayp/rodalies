"""Probability that a Rodalies trip is cancelled or 15+ minutes late, and how it is scored."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

NUMERIC = ["known_canceled", "known_late", "visible", "line_cancel_share", "line_late_share",
           "line_visibility", "global_cancel_share", "hour_sin", "hour_cos", "weekend", "strike_day",
           "lead_min"]
FEED_ONLY = ["known_canceled", "known_late"]   # what the feed already says about this trip
EPS = 1e-4


class BaseRate:
    """Same probability for every trip: the training disruption rate."""
    def fit(self, X, y):
        self.p = float(np.mean(y))
        return self
    def predict(self, X):
        return np.full(len(X), self.p)


class FeedOnly:
    """Trust the feed: logistic on whether it already flags this trip."""
    def fit(self, X, y):
        self.m = LogisticRegression(max_iter=1000).fit(X[FEED_ONLY], y)
        return self
    def predict(self, X):
        return self.m.predict_proba(X[FEED_ONLY])[:, 1]


class LineState:
    """Feed flags plus the current state of the line and the day (what we add)."""
    def fit(self, X, y):
        self.mu, self.sd = X[NUMERIC].mean(), X[NUMERIC].std().replace(0, 1)
        self.m = LogisticRegression(max_iter=2000, C=0.5).fit((X[NUMERIC] - self.mu) / self.sd, y)
        return self
    def predict(self, X):
        return self.m.predict_proba((X[NUMERIC] - self.mu) / self.sd)[:, 1]


MODELS = {"base rate": BaseRate, "feed only": FeedOnly, "feed + line state": LineState}


def split_by_day(ex: pd.DataFrame, test_frac: float = 0.3):
    days = sorted(ex.service_date.unique())
    cut = max(1, int(round(len(days) * (1 - test_frac))))
    train_days = set(days[:cut])
    return ex[ex.service_date.isin(train_days)], ex[~ex.service_date.isin(train_days)]


def score(y, p) -> dict:
    p = np.clip(p, EPS, 1 - EPS)
    out = {"brier": brier_score_loss(y, p), "logloss": log_loss(y, p, labels=[0, 1]), "n": int(len(y)),
           "rate": float(np.mean(y))}
    out["auc"] = roc_auc_score(y, p) if len(set(y)) == 2 else float("nan")
    return out


def split_by_departure(ex: pd.DataFrame, test_frac: float = 0.3):
    """Preliminary split inside one or two days: test on the trips that depart last."""
    dep = ex.t + ex.lead_min * 60
    cut = dep.quantile(1 - test_frac)
    return ex[dep < cut], ex[dep >= cut]


def trip_bootstrap(test: pd.DataFrame, preds: dict, a: str, b: str, n: int = 1000, seed: int = 0):
    """95% interval for Brier(a) - Brier(b), resampling whole trips (examples of one trip are not independent)."""
    ids, inv = np.unique(test.trip_id.values + "|" + test.service_date.values, return_inverse=True)
    ea = (preds[a] - test.y.values) ** 2
    eb = (preds[b] - test.y.values) ** 2
    rng, out = np.random.default_rng(seed), []
    for _ in range(n):
        w = np.bincount(rng.integers(0, len(ids), len(ids)), minlength=len(ids))[inv]
        out.append(((ea - eb) * w).sum() / w.sum())
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def evaluate(ex: pd.DataFrame, min_days: int = 3, preliminary: bool = False) -> dict:
    days = ex.service_date.nunique()
    prelim = days < min_days
    if len(ex) < 200 or (prelim and not preliminary):
        return {"ok": False, "reason": f"only {days} service day(s) and {len(ex)} examples; need at least "
                                       f"{min_days} days to hold one out, so no performance is claimed "
                                       f"(use --preliminary for a labelled first reading once there are 200+ examples)"}
    train, test = (split_by_departure(ex) if prelim else split_by_day(ex))
    res, preds = {}, {}
    for name, cls in MODELS.items():
        m = cls().fit(train, train.y.values)
        preds[name] = m.predict(test)
        res[name] = score(test.y.values, preds[name])
    lo, hi = trip_bootstrap(test, preds, "feed + line state", "feed only")
    return {"ok": True, "preliminary": prelim,
            "note": ("PRELIMINARY: fewer than %d service days; the test set is the trips that depart last, "
                     "and one day of one weekday type may not represent the network." % min_days) if prelim else "",
            "train_trips": int(train.trip_id.nunique()), "test_trips": int(test.trip_id.nunique()),
            "scores": res,
            "brier_gain_line_state_vs_feed_only": float(res["feed only"]["brier"] - res["feed + line state"]["brier"]),
            "brier_gain_ci95": [-hi, -lo]}
