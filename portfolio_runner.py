"""Run several model backends against the current BitGN agent in parallel.

This is orchestration only: each profile delegates to run_parallel.py with its
own log directory and with RESULTS.md appends disabled to avoid concurrent file
writes. The BitGN run submission behavior remains run_parallel.py's behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path


DEFAULT_PROFILES = (
    ("codex53", "codex:gpt-5.3-codex", 6),
    ("sonnet", "claude:sonnet", 4),
    ("agy", "agy", 4),
)

FINAL_RE = re.compile(
    r"FINAL:\s+(?P<pct>\d+(?:\.\d+)?)%\s+\("
    r"(?P<perfect>\d+)/(?P<total>\d+)\s+perfect,\s+"
    r"(?P<scored>\d+)\s+scored\)"
)
SPEED_RE = re.compile(
    r"SPEED:\s+wall\s+(?P<wall>\d+)s\s+\|\s+"
    r"avg/task\s+(?P<avg>\d+)s\s+\|\s+"
    r"slowest\s+(?P<slowest>\d+)s\s+\|\s+"
    r"parallel\s+(?P<parallel>\d+)"
)


@dataclass(frozen=True)
class Profile:
    name: str
    model_id: str
    parallel: int


@dataclass
class RunSummary:
    pct: float | None = None
    perfect: int | None = None
    total: int | None = None
    scored: int | None = None
    wall_seconds: int | None = None
    avg_task_seconds: int | None = None
    slowest_seconds: int | None = None
    parallel: int | None = None


@dataclass
class ProfileResult:
    profile: Profile
    returncode: int
    elapsed_seconds: float
    out_dir: str
    command: list[str]
    summary: RunSummary


def parse_run_summary(output: str) -> RunSummary:
    summary = RunSummary()
    if final := FINAL_RE.search(output):
        summary.pct = float(final.group("pct"))
        summary.perfect = int(final.group("perfect"))
        summary.total = int(final.group("total"))
        summary.scored = int(final.group("scored"))
    if speed := SPEED_RE.search(output):
        summary.wall_seconds = int(speed.group("wall"))
        summary.avg_task_seconds = int(speed.group("avg"))
        summary.slowest_seconds = int(speed.group("slowest"))
        summary.parallel = int(speed.group("parallel"))
    return summary


def build_env(profile: Profile, base_out_dir: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    profile_out = base_out_dir / profile.name
    env.update(
        {
            "MODEL_ID": profile.model_id,
            "PARALLEL": str(profile.parallel),
            "SWEEP_LOG_DIR": str(profile_out / "tasks"),
            "NO_RESULTS_APPEND": "1",
        }
    )
    return env


async def run_profile(profile: Profile, tasks: list[str], base_out_dir: Path) -> ProfileResult:
    profile_out = base_out_dir / profile.name
    tasks_out = profile_out / "tasks"
    tasks_out.mkdir(parents=True, exist_ok=True)
    command = ["uv", "run", "python", "run_parallel.py", *tasks]
    env = build_env(profile, base_out_dir)
    started = time.time()

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=Path(__file__).resolve().parent,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    chunks: list[str] = []
    log_path = profile_out / "runner.log"
    with log_path.open("w", encoding="utf-8") as log:
        assert process.stdout is not None
        async for raw in process.stdout:
            text = raw.decode("utf-8", errors="replace")
            chunks.append(text)
            log.write(text)
            log.flush()
            for line in text.rstrip().splitlines():
                print(f"[{profile.name}] {line}", flush=True)

    returncode = await process.wait()
    output = "".join(chunks)
    return ProfileResult(
        profile=profile,
        returncode=returncode,
        elapsed_seconds=time.time() - started,
        out_dir=str(profile_out),
        command=command,
        summary=parse_run_summary(output),
    )


def parse_profile(value: str) -> Profile:
    try:
        name, rest = value.split(":", 1)
        model_id, parallel_raw = rest.rsplit(":", 1)
        return Profile(name=name, model_id=model_id, parallel=int(parallel_raw))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "profile must be name:model_id:parallel, for example codex53:codex:gpt-5.3-codex:6"
        ) from exc


def default_out_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    return Path("artifacts") / "portfolio" / stamp


def write_summary(results: list[ProfileResult], out_dir: Path, tasks: list[str]) -> None:
    payload = {
        "created_utc": datetime.now(UTC).isoformat(),
        "tasks": tasks or None,
        "results": [
            {
                **asdict(result),
                "profile": asdict(result.profile),
                "summary": asdict(result.summary),
            }
            for result in results
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Portfolio Runner Summary",
        "",
        f"- created_utc: `{payload['created_utc']}`",
        f"- tasks: `{', '.join(tasks) if tasks else 'full sweep'}`",
        "",
        "| profile | model | rc | perfect | score | wall | elapsed | logs |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        summary = result.summary
        perfect = (
            f"{summary.perfect}/{summary.total}"
            if summary.perfect is not None and summary.total is not None
            else "n/a"
        )
        score = f"{summary.pct:.2f}%" if summary.pct is not None else "n/a"
        wall = f"{summary.wall_seconds}s" if summary.wall_seconds is not None else "n/a"
        lines.append(
            "| "
            f"{result.profile.name} | {result.profile.model_id} | {result.returncode} | "
            f"{perfect} | {score} | {wall} | {result.elapsed_seconds:.0f}s | "
            f"{result.out_dir} |"
        )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="*", help="Optional task ids, for example t16 t45")
    parser.add_argument("--out-dir", type=Path, default=default_out_dir())
    parser.add_argument(
        "--profile",
        action="append",
        type=parse_profile,
        help="Override profiles. Format: name:model_id:parallel",
    )
    args = parser.parse_args(argv)

    profiles = args.profile or [Profile(*item) for item in DEFAULT_PROFILES]
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"portfolio out: {out_dir}")
    print("profiles: " + ", ".join(f"{p.name}={p.model_id}@p{p.parallel}" for p in profiles))
    if args.tasks:
        print("tasks: " + ", ".join(args.tasks))
    else:
        print("tasks: full sweep")

    results = await asyncio.gather(*(run_profile(profile, args.tasks, out_dir) for profile in profiles))
    write_summary(results, out_dir, args.tasks)

    print(f"\nsummary: {out_dir / 'SUMMARY.md'}")
    return 0 if all(result.returncode == 0 for result in results) else 1


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
