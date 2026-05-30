"""Extract BitGN public run scorer feedback from evaluated/open run pages.

This is intentionally stdlib-only so it can run during contest operations
without installing browser or HTML parsing dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


def _clean_text(text: str) -> str:
    return " ".join(unescape(text).split())


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return _clean_text(" ".join(self.parts))


class _RunRowsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._td_index = -1
        self._in_a = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        if tag == "tr":
            self._row = {"trial_id": "", "trial_url": "", "task": "", "numeric": []}
            self._td_index = -1
        elif self._row is not None and tag == "td":
            self._td_index += 1
        elif self._row is not None and tag == "a":
            self._in_a = True
            href = attr.get("href", "")
            if href:
                self._row["trial_url"] = href
        elif self._row is not None and tag == "div" and attr.get("class") == "task-text":
            self._row["task"] = _clean_text(attr.get("title", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_a = False
        elif tag == "tr" and self._row is not None:
            nums = self._row.get("numeric", [])
            if self._row.get("trial_id") and self._row.get("task") and len(nums) >= 3:
                self._row["time"] = nums[0]
                self._row["steps"] = int(float(nums[1]))
                self._row["score"] = float(nums[2])
                del self._row["numeric"]
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._row is None:
            return
        text = data.strip()
        if not text:
            return
        if self._in_a and re.fullmatch(r"t\d+", text):
            self._row["trial_id"] = text
        elif self._td_index in (3, 4, 5):
            self._row["numeric"].append(text)


def _first_match(pattern: str, html: str, default: str = "") -> str:
    match = re.search(pattern, html, re.S | re.I)
    if not match:
        return default
    return _clean_text(match.group(1))


def _stats(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for label, value in re.findall(
        r'<div class="stat__label">(.*?)</div>\s*<div class="stat__value">(.*?)</div>',
        html,
        re.S | re.I,
    ):
        out[_clean_text(label).lower().replace(" ", "_")] = _clean_text(value)
    return out


def _meta(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for label, value in re.findall(
        r'<div class="meta__label">(.*?)</div>\s*<div class="meta__value[^"]*">(.*?)</div>',
        html,
        re.S | re.I,
    ):
        out[_clean_text(label).lower().replace(" ", "_")] = _clean_text(re.sub(r"<[^>]+>", " ", value))
    return out


def parse_run_html(html: str, url: str = "") -> dict[str, Any]:
    rows = _RunRowsParser()
    rows.feed(html)
    trials = rows.rows
    score_sum = round(sum(float(row["score"]) for row in trials), 4)
    summary = {
        "trial_count": len(trials),
        "points_sum": score_sum,
        "perfect": sum(1 for row in trials if row["score"] == 1.0),
        "zero": sum(1 for row in trials if row["score"] == 0.0),
        "partial": sum(1 for row in trials if 0.0 < row["score"] < 1.0),
    }
    return {
        "url": url,
        "benchmark": _first_match(r"<h1>(.*?)</h1>", html),
        "run_id": _first_match(r'<span class="mono">(run-[^<]+)</span>', html),
        "state": _first_match(r'<span class="badge [^"]+">([^<]+)</span>', html),
        "meta": _meta(html),
        "stats": _stats(html),
        "summary": summary,
        "trials": trials,
    }


def _html_text(html: str) -> str:
    parser = _TextParser()
    parser.feed(html)
    return parser.text()


def classify_detail(detail: str, score: float | None = None) -> str:
    low = detail.lower()
    if "expected outcome outcome_denied_security, got outcome_ok" in low:
        return "security_miss"
    if "expected outcome outcome_denied_security" in low:
        return "security_outcome_mismatch"
    if "expected outcome" in low:
        return "outcome_mismatch"
    if "answer refs for family" in low or "missing required reference" in low:
        return "ref_mismatch"
    if "answer amount mismatch" in low:
        return "amount_mismatch"
    if "answer should be" in low:
        return "expected_answer"
    if "expected only file changes" in low:
        return "file_change_mismatch"
    if score == 0.0:
        return "full_miss"
    if score is not None and 0.0 < score < 1.0:
        return "partial"
    return "unknown"


def parse_trial_log_html(html: str) -> dict[str, Any]:
    text = _html_text(html)
    match = re.search(
        r"AI agent score\s+([0-9]+(?:\.[0-9]+)?)(.*?)(?:Runtime event stream completed|BitGN trial closed|Polling stopped|$)",
        text,
        re.S | re.I,
    )
    if not match:
        return {"score": None, "detail": "", "classification": "unknown"}
    score = float(match.group(1))
    detail = _clean_text(match.group(2))
    detail = re.sub(r"\s*\[\s*OK\s*\].*$", "", detail).strip()
    return {
        "score": score,
        "detail": detail,
        "classification": classify_detail(detail, score),
    }


def fetch_url(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def collect_feedback(run_url: str, include_perfect: bool = False) -> dict[str, Any]:
    run = parse_run_html(fetch_url(run_url), run_url)
    for trial in run["trials"]:
        if trial["score"] == 1.0 and not include_perfect:
            continue
        if not trial.get("trial_url"):
            continue
        try:
            feedback = parse_trial_log_html(fetch_url(trial["trial_url"]))
        except Exception as exc:
            feedback = {"score": None, "detail": str(exc), "classification": "fetch_error"}
        trial["feedback"] = feedback
    classes: dict[str, int] = {}
    for trial in run["trials"]:
        cls = trial.get("feedback", {}).get("classification")
        if cls:
            classes[cls] = classes.get(cls, 0) + 1
    run["summary"]["feedback_classes"] = dict(sorted(classes.items()))
    return run


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Score Feedback: {report.get('run_id') or report.get('url')}",
        "",
        f"- Benchmark: `{report.get('benchmark', '')}`",
        f"- State: `{report.get('state', '')}`",
        f"- Public score: `{report.get('stats', {}).get('score', '')}`",
        f"- Summed task points: `{summary['points_sum']}/{summary['trial_count']}`",
        f"- Perfect: `{summary['perfect']}`",
        f"- Zero: `{summary['zero']}`",
        f"- Partial: `{summary['partial']}`",
        f"- Total trial time: `{report.get('stats', {}).get('total_trial_time', '')}`",
        "",
        "## Feedback Classes",
        "",
    ]
    for cls, count in summary.get("feedback_classes", {}).items():
        lines.append(f"- `{cls}`: {count}")
    lines += ["", "## Non-Perfect Trials", "", "| trial | score | class | detail | task |", "|---|---:|---|---|---|"]
    for trial in report["trials"]:
        if trial["score"] == 1.0:
            continue
        feedback = trial.get("feedback", {})
        detail = str(feedback.get("detail", "")).replace("|", "\\|")
        task = str(trial.get("task", "")).replace("|", "\\|")
        lines.append(
            f"| `{trial['trial_id']}` | {trial['score']:.2f} | `{feedback.get('classification', '')}` | "
            f"{detail[:260]} | {task[:180]} |"
        )
    return "\n".join(lines) + "\n"


def write_feedback(report: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    json_path = path / "score_feedback.json"
    md_path = path / "score_feedback.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_url", help="Public BitGN run URL")
    parser.add_argument("--out-dir", default="", help="Directory for score_feedback.json/md")
    parser.add_argument("--include-perfect", action="store_true", help="Fetch trial logs for perfect trials too")
    args = parser.parse_args(argv)

    report = collect_feedback(args.run_url, include_perfect=args.include_perfect)
    if args.out_dir:
        json_path, md_path = write_feedback(report, args.out_dir)
        print(f"wrote {json_path}")
        print(f"wrote {md_path}")
    else:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
