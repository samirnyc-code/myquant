"""Overnight batch — runs all analyses sequentially.

Order:
1. Per-setup multileg ES (already running separately — skip if results exist)
2. Per-setup singleleg ES
3. Per-setup multileg MES x5
4. Per-setup singleleg MES x5
5. Time-of-day analysis
6. ER timing comparison
7. Fade hypothesis analysis

Each job is a subprocess call so a crash in one doesn't kill the rest.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(_ROOT / ".venv" / "Scripts" / "python.exe")
SCRIPTS = _ROOT / "scripts"
LOG = _ROOT / "docs" / "living" / "overnight_batch_log.txt"


def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {m}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run_job(name, cmd):
    log(f"START: {name}")
    log(f"  cmd: {' '.join(cmd)}")
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=str(_ROOT), capture_output=False,
                            creationflags=0x08000000)   # CREATE_NO_WINDOW: no child console flash
    elapsed = time.perf_counter() - t0
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    log(f"END:   {name} — {status} — {elapsed/60:.1f} min")
    return result.returncode == 0


def main():
    with open(LOG, "w") as f:
        f.write(f"Overnight batch started: {datetime.now()}\n\n")

    t_start = time.perf_counter()

    jobs = [
        ("Per-setup singleleg ES",
         [PYTHON, str(SCRIPTS / "per_setup_portfolio.py"), "--mode", "singleleg"]),

        ("Per-setup multileg MES x5",
         [PYTHON, str(SCRIPTS / "per_setup_portfolio.py"), "--mode", "multileg",
          "--instrument", "MES", "--contracts", "5"]),

        ("Per-setup singleleg MES x5",
         [PYTHON, str(SCRIPTS / "per_setup_portfolio.py"), "--mode", "singleleg",
          "--instrument", "MES", "--contracts", "5"]),

        ("Time-of-day analysis",
         [PYTHON, str(SCRIPTS / "late_period_analysis.py")]),

        ("ER timing comparison",
         [PYTHON, str(SCRIPTS / "er_timing_compare.py")]),

        ("Fade hypothesis analysis",
         [PYTHON, str(SCRIPTS / "fade_analysis.py")]),
    ]

    results = {}
    for name, cmd in jobs:
        ok = run_job(name, cmd)
        results[name] = ok

    elapsed_total = time.perf_counter() - t_start
    log(f"\n{'='*60}")
    log(f"BATCH COMPLETE — {elapsed_total/60:.1f} min total")
    log(f"{'='*60}")
    for name, ok in results.items():
        log(f"  {'OK' if ok else 'FAIL'}  {name}")

    # Write summary to its own file
    summary_file = _ROOT / "docs" / "living" / "overnight_summary.md"
    with open(summary_file, "w") as f:
        f.write(f"# Overnight Batch Results\n\n")
        f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Total runtime:** {elapsed_total/60:.1f} min\n\n")
        f.write("## Job status\n\n")
        f.write("| Job | Status | \n")
        f.write("|-----|--------|\n")
        for name, ok in results.items():
            f.write(f"| {name} | {'OK' if ok else 'FAILED'} |\n")
        f.write("\n## Output files\n\n")
        f.write("All reports in `docs/living/`:\n\n")
        f.write("- `per_setup_singleleg_ES1_*.md` — singleleg ES optimization\n")
        f.write("- `per_setup_multileg_MES5_*.md` — multileg MES x5 optimization\n")
        f.write("- `per_setup_singleleg_MES5_*.md` — singleleg MES x5 optimization\n")
        f.write("- `tod_analysis.md` — time-of-day signal analysis\n")
        f.write("- `er_timing_compare.md` — ER bar T vs T-1 comparison\n")
        f.write("- `fade_analysis.md` — fade hypothesis on losing trades\n")
    log(f"Summary saved: {summary_file}")


if __name__ == "__main__":
    main()
