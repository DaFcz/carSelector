"""Covers app/ui/admin.py's JobState - the generic subprocess-streaming
mechanism both admin buttons share. Doesn't invoke the real scraper/import
scripts (network calls, minutes of runtime) - a trivial subprocess
exercises the same streaming/completion code path.
"""

import sys

from app.ui.admin import JobProgress, JobState, estimate_remaining, format_duration, parse_progress


async def test_job_state_streams_output_and_completes() -> None:
    state = JobState()
    refresh_calls = 0

    def on_output() -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    await state.run([sys.executable, "-c", "print('line one'); print('line two')"], on_output)

    assert state.lines == ["line one", "line two"]
    assert state.return_code == 0
    assert state.is_running is False
    assert refresh_calls >= 3  # start + >=1 per line + completion


async def test_job_state_captures_nonzero_exit_code() -> None:
    state = JobState()
    await state.run([sys.executable, "-c", "import sys; sys.exit(2)"], lambda: None)
    assert state.return_code == 2
    assert state.is_running is False


async def test_job_state_is_a_noop_while_already_running() -> None:
    state = JobState()
    state.is_running = True
    await state.run([sys.executable, "-c", "print('should not run')"], lambda: None)
    assert state.lines == []


async def test_job_state_turns_progress_lines_into_progress_not_log() -> None:
    state = JobState()
    script = (
        "print('Active source: skoda'); "
        'print(\'PROGRESS {"step": 2, "steps": 4, "item": "skoda", "sub": 1, "subs": 2}\')'
    )
    await state.run([sys.executable, "-c", script], lambda: None)

    assert state.lines == ["Active source: skoda"]
    assert state.progress == JobProgress(step=2, steps=4, item="skoda", sub=1, subs=2)
    assert state.duration is not None and state.elapsed == state.duration


def test_parse_progress_ignores_ordinary_and_malformed_lines() -> None:
    assert parse_progress("Active source: skoda") is None
    assert parse_progress("PROGRESS {not json") is None
    assert parse_progress('PROGRESS {"item": "x"}') is None
    assert parse_progress('PROGRESS {"step": 1, "steps": 3, "item": "kia"}') == JobProgress(1, 3, "kia")


def test_progress_fraction_counts_finished_steps_plus_the_current_steps_share() -> None:
    assert JobProgress(1, 4, "a").fraction == 0.0
    assert JobProgress(3, 4, "a", sub=1, subs=2).fraction == 0.625
    assert JobProgress(2, 4, "a", sub=0, subs=0).fraction == 0.25  # source with no new documents


def test_estimate_remaining() -> None:
    assert estimate_remaining(10, 0.0, None) is None  # nothing to go on yet
    assert estimate_remaining(60, 0.0, 300) == 240  # history only
    assert estimate_remaining(400, 0.0, 300) is None  # slower than last time, no progress yet
    assert estimate_remaining(100, 0.5, None) == 100  # progress only
    # Both: weighted by how far the run is (here 50/50 of 100 and 200).
    assert estimate_remaining(100, 0.5, 300) == 150


def test_format_duration() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(247.4) == "4:07"


def test_job_state_runs_on_a_selector_event_loop() -> None:
    # `uvicorn --reload` on Windows runs the app on a SelectorEventLoop,
    # which can't start asyncio subprocesses - the job used to hang on
    # "running" forever there. pytest's own loop (Proactor) hid that.
    import asyncio

    state = JobState()
    loop = asyncio.SelectorEventLoop()
    try:
        loop.run_until_complete(state.run([sys.executable, "-c", "print('hello')"], lambda: None))
    finally:
        loop.close()

    assert state.lines == ["hello"]
    assert state.return_code == 0
    assert state.is_running is False


async def test_job_state_that_cannot_start_ends_as_failed_not_running() -> None:
    state = JobState()
    await state.run(["definitely-not-a-real-executable-xyz"], lambda: None)

    assert state.is_running is False
    assert state.return_code == -1
    assert state.lines and "FileNotFoundError" in state.lines[0]
