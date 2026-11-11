"""Decide whether a scheduled run has anything to do.

    python -m pipeline.check --live https://<owner>.github.io/<repo>/data/manifest.json \
        --commit "$GITHUB_SHA" --event "$GITHUB_EVENT_NAME"

GitHub starts scheduled workflows late or not at all (observed: one of two evening runs,
hours late), so the workflow now runs every hour and this check makes most of those runs
stop after a few seconds: a build happens only when ECMWF has a newer complete run than the
one on the site, or the site was built from different code, or it is missing something.

Prints the decision and, inside GitHub Actions, writes `build=true|false` to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from . import catalogue
from .process import iso_utc


def needs_build(event: str, newest_run_utc: str, commit: str, live: dict | None) -> tuple[bool, str]:
    """(build?, reason). `live` is the manifest the site serves now, or None if unreadable."""
    if event != "schedule":
        return True, f"triggered by {event}: always build"
    if not live:
        return True, "the live manifest could not be read"
    live_run = (live.get("run") or {}).get("reference_utc")
    if not live_run:
        return True, "the live manifest names no run"
    # ISO 8601 UTC strings in one fixed format compare correctly as text
    if live_run < newest_run_utc:
        return True, f"ECMWF has run {newest_run_utc}, the site shows {live_run}"
    live_commit = (live.get("build") or {}).get("commit")
    if live_commit != commit:
        return True, f"the site was built from {live_commit or 'an unknown commit'}, the code is now {commit}"
    status = (live.get("ensemble") or {}).get("status")
    if status != "ok":
        return True, f"the site's ensemble status is {status!r}; trying again"
    return False, f"the site already shows run {live_run} built from {commit}"


def read_live_manifest(session, url: str) -> dict | None:
    try:
        r = session.get(url, params={"t": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")},
                        headers={"Cache-Control": "no-cache"}, timeout=catalogue.TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", required=True, help="URL of the manifest the site serves")
    p.add_argument("--commit", required=True)
    p.add_argument("--event", required=True, help="GitHub event name: schedule, push, workflow_dispatch")
    a = p.parse_args(argv)

    if a.event != "schedule":
        build, reason = needs_build(a.event, "", a.commit, None)
    else:
        session = catalogue.new_session()
        newest = catalogue.latest_complete_run(session, datetime.now(timezone.utc), with_ensemble=True)
        build, reason = needs_build(a.event, iso_utc(newest.reference_time), a.commit, read_live_manifest(session, a.live))
    print(f"build={'true' if build else 'false'}: {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"build={'true' if build else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
