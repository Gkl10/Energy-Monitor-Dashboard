"""
run_local.py
============
Runs scraper.py and, if new data was found, automatically commits
and pushes data.json to GitHub.

Usage (from the project root):
    python run_local.py

Requirements:
  - git must be installed and available on PATH
  - The repo must already have a remote named 'origin' configured
  - Your local git identity (user.name / user.email) should already be set,
    or set GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL env vars before running.
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime

# Import main() from scraper.py in the same directory
import scraper


def run_git(args: list[str]) -> subprocess.CompletedProcess:
    """Run a git command, print the output, and raise on failure."""
    cmd = ["git"] + args
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        print(f"\n[ERROR] git command failed (exit code {result.returncode})")
        sys.exit(result.returncode)
    return result


def main():
    print("=" * 60)
    print("  Local Scraper Runner")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # Step 1: Run the scraper
    # ------------------------------------------------------------------ #
    print("\n[1/3] Running scraper...\n")
    new_count = scraper.main()

    # ------------------------------------------------------------------ #
    # Step 2: Check if new data was written
    # ------------------------------------------------------------------ #
    if not new_count:
        print("\n[2/3] No new entries — nothing to commit.")
        print("\nDone.")
        return

    print(f"\n[2/3] {new_count} new report(s) found. Syncing files and committing...\n")

    # Copy data.json into the dashboard folder so GitHub Pages serves fresh data
    dashboard_json = os.path.join("dashboard", "data.json")
    if os.path.isdir("dashboard"):
        shutil.copy("data.json", dashboard_json)
        print(f"  Copied data.json → {dashboard_json}")
    else:
        print("  [WARN] 'dashboard/' folder not found — skipping dashboard sync.")
        dashboard_json = None

    # ------------------------------------------------------------------ #
    # Step 3: Commit and push
    # ------------------------------------------------------------------ #
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"auto: update daily energy metrics ({timestamp})"

    files_to_stage = ["data.json"]
    if dashboard_json and os.path.exists(dashboard_json):
        files_to_stage.append(dashboard_json)

    run_git(["add"] + files_to_stage)
    run_git(["commit", "-m", commit_msg])
    run_git(["push", "--set-upstream", "origin", "HEAD"])

    print(f"\n[3/3] Successfully pushed {new_count} new report(s) to GitHub.")
    print("\nDone.")


if __name__ == "__main__":
    main()
