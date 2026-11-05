"""The bridge's command line: the real vehicle's throttle cap.

The controls' own default cap is 90 percent, a hardware limit. Teleop
through the bridge starts at 20 percent (the bench's walking-pace duty on
the jack, 13 Oct 2026) and is raised only by an explicit flag.
"""
import pytest

from bridge.__main__ import build_parser, controls_kwargs


def test_the_throttle_cap_defaults_to_twenty_percent():
    args = build_parser().parse_args([])
    assert controls_kwargs(args)["max_duty"] == 20


def test_the_throttle_cap_is_raised_only_by_the_flag():
    args = build_parser().parse_args(["--max-duty", "30"])
    assert controls_kwargs(args)["max_duty"] == 30


@pytest.mark.parametrize("bad", ["-1", "91", "abc"])
def test_a_cap_outside_zero_to_ninety_is_refused(bad):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--max-duty", bad])


def test_steer_sense_reaches_the_controls():
    args = build_parser().parse_args(["--steer-sense", "left_increases"])
    assert controls_kwargs(args)["steer_sense"] == "left_increases"



def test_the_bench_waiver_is_off_unless_asked_for():
    from bridge.__main__ import waived_checks
    assert waived_checks(build_parser().parse_args([])) == ()
    args = build_parser().parse_args(["--vehicle", "ugv01", "--bench-on-jack"])
    assert waived_checks(args) == ("stop_on_link_loss",)


def test_a_snapshot_request_reads_status_through_the_bridge_and_logs_the_controls():
    """5 Nov 2026: the Jetson session needed the board's state (STATUS, the
    brake angle) while the bridge holds the ports. SIGUSR1 asks the bridge
    itself, the one writer, for a fresh STATUS and logs the snapshot."""
    from bridge.__main__ import log_snapshot

    class Controls:
        reads = 0
        def read_status(self): self.reads += 1
        def snapshot(self): return {"drive": {"status_raw": "GR=01,BR=00"}, "brake": {"angle_deg": 174.0}}

    class Log:
        def __init__(self): self.events = []
        def event(self, name, **kw): self.events.append((name, kw))

    c, log = Controls(), Log()
    log_snapshot(c, log, wait_s=0)
    assert c.reads == 1
    assert log.events == [("snapshot", {"drive": {"status_raw": "GR=01,BR=00"}, "brake": {"angle_deg": 174.0}})]


def test_brake_absent_needs_the_jack_waiver_and_reaches_the_controls():
    from bridge.__main__ import check_bench_flags
    args = build_parser().parse_args(["--vehicle", "ugv01", "--bench-on-jack", "--bench-brake-absent"])
    assert controls_kwargs(args)["brake_absent"] is True
    assert check_bench_flags(args) is None
    alone = build_parser().parse_args(["--vehicle", "ugv01", "--bench-brake-absent"])
    assert "bench-on-jack" in check_bench_flags(alone)
    assert controls_kwargs(build_parser().parse_args([]))["brake_absent"] is False
