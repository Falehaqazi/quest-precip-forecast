from pipeline.check import needs_build

NEWEST = "2026-11-11T00:00:00Z"
COMMIT = "abc123"


def live(run=NEWEST, commit=COMMIT, ensemble="ok"):
    m = {"run": {"reference_utc": run}}
    if commit is not None:
        m["build"] = {"commit": commit}
    if ensemble is not None:
        m["ensemble"] = {"status": ensemble}
    return m


def test_nothing_new_means_no_build():
    build, reason = needs_build("schedule", NEWEST, COMMIT, live())
    assert build is False
    assert NEWEST in reason


def test_a_newer_ecmwf_run_triggers_a_build():
    build, reason = needs_build("schedule", NEWEST, COMMIT, live(run="2026-11-10T12:00:00Z"))
    assert build is True
    assert "2026-11-10T12:00:00Z" in reason and NEWEST in reason


def test_run_comparison_is_by_time_across_days_months_and_years():
    assert needs_build("schedule", "2026-11-11T00:00:00Z", COMMIT, live(run="2026-11-10T12:00:00Z"))[0]
    assert needs_build("schedule", "2026-12-01T00:00:00Z", COMMIT, live(run="2026-11-30T12:00:00Z"))[0]
    assert needs_build("schedule", "2027-01-01T00:00:00Z", COMMIT, live(run="2026-12-31T12:00:00Z"))[0]
    # the site is never ahead of ECMWF in practice, but if it were there is nothing to build
    assert not needs_build("schedule", "2026-11-10T12:00:00Z", COMMIT, live(run=NEWEST))[0]


def test_pushes_and_manual_runs_always_build():
    assert needs_build("push", NEWEST, COMMIT, live())[0] is True
    assert needs_build("workflow_dispatch", NEWEST, COMMIT, live())[0] is True


def test_code_that_was_never_deployed_triggers_a_build():
    # e.g. after a deploy that timed out: same ECMWF run, but the site is from older code
    assert needs_build("schedule", NEWEST, COMMIT, live(commit="older"))[0] is True
    assert needs_build("schedule", NEWEST, COMMIT, live(commit=None))[0] is True


def test_missing_probabilities_are_retried():
    assert needs_build("schedule", NEWEST, COMMIT, live(ensemble="unavailable"))[0] is True
    assert needs_build("schedule", NEWEST, COMMIT, live(ensemble=None))[0] is True


def test_an_unreadable_or_odd_live_manifest_triggers_a_build():
    assert needs_build("schedule", NEWEST, COMMIT, None)[0] is True
    assert needs_build("schedule", NEWEST, COMMIT, {})[0] is True
    assert needs_build("schedule", NEWEST, COMMIT, {"run": {}})[0] is True
