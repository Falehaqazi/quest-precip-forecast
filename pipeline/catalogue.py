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


def find_members(entries: list[dict], **match: str) -> dict[int, tuple[int, int]]:
    """{member number: (offset, length)} for every ensemble message whose keys equal `match`.

    Each member must appear exactly once; a duplicate would silently double-count it.
    """
    out: dict[int, tuple[int, int]] = {}
    for e in entries:
        if all(e.get(k) == v for k, v in match.items()):
            if "number" not in e:
                raise LookupError(f"message matching {match} has no member number")
            n = int(e["number"])
            if n in out:
                raise LookupError(f"member {n} appears more than once for {match}")
            out[n] = (int(e["_offset"]), int(e["_length"]))
    if not out:
        raise LookupError(f"no ensemble messages match {match}")
    return out


def fetch_range(session: requests.Session, url: str, offset: int, length: int) -> bytes:
    """Download one GRIB message by byte range and check it is a whole message."""
    r = session.get(url, headers={"Range": f"bytes={offset}-{offset + length - 1}"}, timeout=TIMEOUT)
    if r.status_code != 206:
        raise IOError(f"expected HTTP 206 for a range request, got {r.status_code}")
    return check_message(r.content, length)


def fetch_message(session: requests.Session, run: Run, step: int, **match: str) -> bytes:
    """Look one field up in the step's index and download just that message."""
    offset, length = find_field(fetch_index(session, run, step), **match)
    return fetch_range(session, run.file_url(step, "grib2"), offset, length)


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


def completeness_urls(run: Run, with_ensemble: bool) -> list[str]:
    """Index files that must exist before a run is used.

    The last step of the deterministic forecast, and (when probabilities are wanted) the last
    step of the ensemble members and of ECMWF's own probability product, which is used as a
    self-check. On 2026-11-10 these appeared at 07:34, 07:40 and 08:01 for the 00z run, so the
    deterministic run is visible for a while before the ensemble is.
    """
    last = expected_steps(run.hour)[-1]
    urls = [run.file_url(last, "index")]
    if with_ensemble:
        urls.append(Run(run.date, run.hour, stream="enfo", type="ef").file_url(last, "index"))
        urls.append(Run(run.date, run.hour, stream="enfo", type="ep").file_url(last, "index"))
    return urls


def latest_complete_run(session: requests.Session, now: datetime, with_ensemble: bool = False) -> Run:
    """Newest 00z/12z run for which every file in completeness_urls() exists."""
    for run in candidate_runs(now):
        if all(session.head(u, timeout=TIMEOUT).status_code == 200 for u in completeness_urls(run, with_ensemble)):
            return run
    raise LookupError("no complete run found in the last few days")
