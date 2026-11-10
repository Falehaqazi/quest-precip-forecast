"""ECMWF open data catalogue: URL layout, index files, byte-range fetches.

Layout verified against https://data.ecmwf.int/forecasts/ on 2026-11-10:
  /forecasts/YYYYMMDD/HHz/ifs/0p25/oper/YYYYMMDDHH0000-{step}h-oper-fc.grib2 (+ .index)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://data.ecmwf.int/forecasts"
USER_AGENT = "precip-forecast-pipeline (python-requests)"
TIMEOUT = 60


@dataclass(frozen=True)
class Run:
    date: str            # YYYYMMDD
    hour: str            # "00" or "12"
    model: str = "ifs"
    resolution: str = "0p25"
    stream: str = "oper"
    type: str = "fc"

    @property
    def directory(self) -> str:
        return f"{BASE_URL}/{self.date}/{self.hour}z/{self.model}/{self.resolution}/{self.stream}"

    def file_url(self, step: int, ext: str) -> str:
        return f"{self.directory}/{self.date}{self.hour}0000-{step}h-{self.stream}-{self.type}.{ext}"

    @property
    def reference_time(self) -> datetime:
        return datetime.strptime(self.date + self.hour, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def expected_steps(hour: str) -> list[int]:
    """Forecast steps (hours) published for a run, as observed in the directory listings."""
    if hour in ("00", "12"):
        return list(range(0, 145, 3)) + list(range(150, 361, 6))
    if hour in ("06", "18"):
        return list(range(0, 145, 3))
    raise ValueError(f"not a run hour: {hour!r}")


def parse_index(text: str) -> list[dict]:
    """The .index file is JSON lines, one per GRIB message."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def find_field(entries: list[dict], **match: str) -> tuple[int, int]:
    """(offset, length) of the single message whose index keys equal `match`."""
    hits = [e for e in entries if all(e.get(k) == v for k, v in match.items())]
    if len(hits) != 1:
        raise LookupError(f"expected exactly one message for {match}, found {len(hits)}")
    return int(hits[0]["_offset"]), int(hits[0]["_length"])


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch_index(session: requests.Session, run: Run, step: int) -> list[dict]:
    r = session.get(run.file_url(step, "index"), timeout=TIMEOUT)
    r.raise_for_status()
    return parse_index(r.text)


def fetch_message(session: requests.Session, run: Run, step: int, **match: str) -> bytes:
    """Download one GRIB message by byte range and check it is a whole message."""
    offset, length = find_field(fetch_index(session, run, step), **match)
    r = session.get(run.file_url(step, "grib2"),
                    headers={"Range": f"bytes={offset}-{offset + length - 1}"}, timeout=TIMEOUT)
    if r.status_code != 206:
        raise IOError(f"expected HTTP 206 for a range request, got {r.status_code}")
    return check_message(r.content, length)


def check_message(data: bytes, expected_length: int) -> bytes:
    if len(data) != expected_length:
        raise IOError(f"got {len(data)} bytes, index says {expected_length}")
    if data[:4] != b"GRIB" or data[-4:] != b"7777":
        raise IOError("byte range is not a complete GRIB message")
    return data


def candidate_runs(now: datetime, hours=("00", "12"), days_back: int = 3) -> list[Run]:
    """Runs at or before `now`, newest first."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    runs = []
    for d in range(days_back + 1):
        day = now - timedelta(days=d)
        for h in sorted(hours, reverse=True):
            run = Run(date=day.strftime("%Y%m%d"), hour=h)
            if run.reference_time <= now:
                runs.append(run)
    return runs


def latest_complete_run(session: requests.Session, now: datetime) -> Run:
    """Newest 00z/12z run whose last step has an index file (taken to mean 'complete')."""
    for run in candidate_runs(now):
        last = expected_steps(run.hour)[-1]
        if session.head(run.file_url(last, "index"), timeout=TIMEOUT).status_code == 200:
            return run
    raise LookupError("no complete run found in the last few days")
