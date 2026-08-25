from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MANIFEST = RESULTS / "run_manifest.json"
STEPS = ["run_regression.py", "run_lint.py", "run_synth.py", "generate_results.py"]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "results",
    "sim_build",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_text(*arguments: str) -> str | None:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        errors="replace",
    )
    if completed.returncode:
        return None
    return completed.stdout.strip()


def source_tree_sha256() -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    source_files = (p for p in ROOT.rglob("*") if p.is_file())
    for path in sorted(source_files, key=lambda p: p.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def write_manifest(payload: dict[str, object]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    commit_sha = git_text("rev-parse", "HEAD")
    dirty_text = git_text("status", "--porcelain=v1")
    source_hash, source_file_count = source_tree_sha256()

    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    RESULTS.mkdir(parents=True)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "started_utc": utc_now(),
        "finished_utc": None,
        "commit_sha": commit_sha,
        "source_tree_sha256": source_hash,
        "source_file_count": source_file_count,
        "source_dirty": bool(dirty_text),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "steps": [],
    }
    write_manifest(manifest)

    for step in STEPS:
        command = [sys.executable, str(ROOT / "scripts" / step)]
        print(f"\n== {step} ==", flush=True)
        started = time.monotonic()
        completed = subprocess.run(command, cwd=ROOT)
        duration = round(time.monotonic() - started, 3)
        step_result = {
            "name": step,
            "command": ["python", f"scripts/{step}"],
            "exit_status": completed.returncode,
            "duration_seconds": duration,
        }
        steps = manifest["steps"]
        assert isinstance(steps, list)
        steps.append(step_result)
        if completed.returncode:
            manifest["status"] = "fail"
            manifest["failed_step"] = step
            manifest["finished_utc"] = utc_now()
            write_manifest(manifest)
            print(
                f"FAILED: {step} exited {completed.returncode}",
                file=sys.stderr,
            )
            return completed.returncode
        write_manifest(manifest)

    manifest["status"] = "pass"
    manifest["finished_utc"] = utc_now()
    write_manifest(manifest)
    print("\nAll required engineering checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
