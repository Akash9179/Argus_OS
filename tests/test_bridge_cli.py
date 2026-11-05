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

