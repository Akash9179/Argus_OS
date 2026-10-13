"""ugv-01 serial protocol encoders and decoders, pure functions.

Frames are checked against what the vehicle itself accepted on 4 Oct 2026
(the team's observations in their serial_control package, copied into the
13 Oct findings) and against the ARGUS DRIVE v4.1.3 spec examples. The
accelerator board shapes come from the same source. If a test here is
wrong, it is wrong in the same way the bench will show; fix the test only
with a bench observation.
"""
from __future__ import annotations

import pytest

from pilot.hal.drivers.ugv01 import protocol as p


# -------------------------------------------------------------- drive board

@pytest.mark.parametrize("frame, expected", [
    (p.info(), b"0x01\n"),
    (p.status(), b"0x16\n"),
    (p.read_steer(), b"0x04\n"),
    (p.read_brake(), b"0x03\n"),
    (p.read_steer_limits(), b"0x10\n"),
    (p.read_brake_limits(), b"0x0F\n"),
    (p.steer("left"), b"0x05 01\n"),
    (p.steer("right"), b"0x05 02\n"),
    (p.steer("stop"), b"0x05 00\n"),
    (p.brake("apply"), b"0x06 01\n"),
    (p.brake("release"), b"0x06 02\n"),
    (p.brake("stop"), b"0x06 00\n"),
    (p.gear("D"), b"0x08 01\n"),
    (p.gear("N"), b"0x08 02\n"),
    (p.gear("R"), b"0x08 03\n"),
    (p.speed_mode(2), b"0x07 02\n"),
    (p.light("off"), b"0x09 00\n"),
    (p.light("ring"), b"0x09 01\n"),
    (p.light("high"), b"0x09 02\n"),
    (p.light("low"), b"0x09 03\n"),
    (p.indicator("off"), b"0x0A 00\n"),
    (p.indicator("left"), b"0x0A 01\n"),
    (p.indicator("right"), b"0x0A 02\n"),
    (p.indicator("park"), b"0x0A 03\n"),
    (p.horn(), b"0x0B 01\n"),
    (p.centre_steer(), b"0x14\n"),
])
def test_drive_frames_are_hex_text_with_space_and_lf(frame, expected):
    assert frame == expected


@pytest.mark.parametrize("call", [
    lambda: p.steer("centre"),
    lambda: p.brake("on"),
    lambda: p.gear("F"),        # the cockpit's F is mapped by the adapter, not here
    lambda: p.speed_mode(0),
    lambda: p.speed_mode(4),
    lambda: p.light("fog"),
    lambda: p.indicator("hazard"),
])
def test_unknown_arguments_raise_not_encode(call):
    with pytest.raises(ValueError):
        call()


def test_no_encoder_exists_for_admin_reset_wifi_or_limit_writes():
    """0x0C reset, 0x0D/0x0E Wi-Fi, 0x11 limit enable, 0x12/0x13 admin
    actuators, and writes to 0x0F/0x10 are not reachable from this module.
    The vehicle must not be reconfigurable or driven past its limits from
    anything above the HAL."""
    for name in ("reset", "wifi", "set_wifi", "admin_steer", "admin_brake",
                 "set_steer_limits", "set_brake_limits", "enable_limits"):
        assert not hasattr(p, name), name
    locked = {0x0C, 0x0D, 0x0E, 0x11, 0x12, 0x13}
    for cmd in p.ALL_COMMANDS:
        assert cmd not in locked


# ------------------------------------------------------------ drive replies

def test_parse_ok_reply_from_the_vehicle():
    r = p.parse_reply("0x01;OK;040103")
    assert r == p.Reply(cmd=0x01, ok=True, data="040103")
    assert p.firmware_version(r.data) == "4.1.3"


def test_parse_err_reply_and_bad_format_from_raw_bytes():
    r = p.parse_reply("0x00;ERR;BAD_FORMAT")
    assert r == p.Reply(cmd=0x00, ok=False, data="BAD_FORMAT")


def test_parse_reply_without_data_and_with_crlf():
    assert p.parse_reply("0x05;OK\r\n") == p.Reply(cmd=0x05, ok=True, data="")


def test_non_reply_lines_are_none_not_errors():
    assert p.parse_reply("") is None
    assert p.parse_reply("hello") is None
    assert p.parse_reply("0xZZ;OK;1") is None


def test_steer_angle_is_one_hex_word_in_tenths_of_a_degree():
    assert p.angle_deg("0601") == 153.7     # read on the vehicle, 13 Oct
    assert p.angle_deg("0263") == 61.1      # brake, same session
    assert p.angle_deg("05D9") == 149.7
    assert p.angle_deg("") is None
    assert p.angle_deg("060") is None
    assert p.angle_deg("xyzw") is None


def test_limits_are_min_then_max_same_units():
    assert p.limits_deg("029E097E") == (67.0, 243.0)
    assert p.limits_deg("097E029E") is None     # min >= max is not a range
    assert p.limits_deg("029E") is None


def test_firmware_version_rejects_other_shapes():
    assert p.firmware_version("AC0102") is None
    assert p.firmware_version("4.1.3") is None


# ----------------------------------------------------------- accelerator board

def test_accel_duty_frame_uses_semicolon_and_hex_byte():
    assert p.accel_duty(0) == b"0x02;00\n"
    assert p.accel_duty(50) == b"0x02;32\n"
    assert p.accel_duty(100) == b"0x02;64\n"
    assert p.ACCEL_ZERO == b"0x02;00\n"
    assert p.accel_info() == b"0x01\n"


@pytest.mark.parametrize("pct", [-1, 101, 1000])
def test_accel_duty_outside_0_100_raises(pct):
    with pytest.raises(ValueError):
        p.accel_duty(pct)


def test_accel_replies():
    assert p.parse_reply("0x01;OK;AC0102") == p.Reply(cmd=0x01, ok=True, data="AC0102")
    assert p.accel_version("AC0102") == "1.2"
    assert p.accel_version("040103") is None
    assert p.parse_reply("0x02;OK;32") == p.Reply(cmd=0x02, ok=True, data="32")
    assert p.parse_reply("0x02;ERR;INVALID_DUTY") == p.Reply(cmd=0x02, ok=False, data="INVALID_DUTY")
    # the board's own shape for an unknown command carries no cmd byte
    assert p.parse_reply("ERR;UNKNOWN_COMMAND") == p.Reply(cmd=None, ok=False, data="UNKNOWN_COMMAND")


def test_decode_line_is_text_when_printable_else_hex():
    assert p.decode_line(b"0x04;OK;0601\r\n") == "0x04;OK;0601"
    assert p.decode_line(b"\xff\x00\n") == "hex: ff 00"
