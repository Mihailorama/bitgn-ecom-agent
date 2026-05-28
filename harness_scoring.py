"""Helpers for reading BitGN scores across harness protocol versions."""

from __future__ import annotations

from typing import Any


def submit_score_available(submit_result: Any) -> bool:
    """Return True when SubmitRunResponse carries final batch scores."""
    return bool(getattr(submit_result, "score_available", False))


def submit_trial_scores(
    submit_result: Any,
    *,
    task_filter: set[str] | None = None,
) -> dict[str, tuple[float | None, list[str], str | None]]:
    """Extract per-task scores from a new-style SubmitRunResponse.

    Older SDKs do not expose `score_available` or `trials`; in that case this
    returns an empty mapping and callers keep the EndTrial scores they already
    collected.
    """
    if not submit_score_available(submit_result):
        return {}

    scores: dict[str, tuple[float | None, list[str], str | None]] = {}
    for trial in getattr(submit_result, "trials", []) or []:
        task_id = str(getattr(trial, "task_id", "") or "")
        if not task_id:
            continue
        if task_filter and task_id not in task_filter:
            continue
        if bool(getattr(trial, "score_available", False)):
            scores[task_id] = (
                float(getattr(trial, "score", 0.0)),
                list(getattr(trial, "score_detail", []) or []),
                None,
            )
        else:
            err = str(getattr(trial, "error", "") or "submit result score unavailable")
            scores[task_id] = (None, [], err)
    return scores


def merge_submit_scores(
    results: list[tuple[Any, ...]],
    submit_result: Any,
    *,
    task_filter: set[str] | None = None,
) -> list[tuple[Any, ...]]:
    """Overlay SubmitRun batch scores onto runner result tuples.

    Runner rows have the shape `(task_id, score, detail, err, secs, ...)`.
    Extra timing/model columns are preserved. Existing worker errors keep
    priority because they mean the local agent execution itself failed.
    """
    batch_scores = submit_trial_scores(submit_result, task_filter=task_filter)
    if not batch_scores:
        return list(results)

    merged: list[tuple[Any, ...]] = []
    for row in results:
        if len(row) < 5:
            merged.append(row)
            continue
        task_id, score, detail, err, *tail = row
        batch = batch_scores.get(str(task_id))
        if batch is None or err:
            merged.append(row)
            continue
        batch_score, batch_detail, batch_err = batch
        if batch_score is None and isinstance(score, (int, float)):
            merged.append(row)
            continue
        merged.append((task_id, batch_score, batch_detail or detail, batch_err, *tail))
    return merged
