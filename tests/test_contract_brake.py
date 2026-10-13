from bridge.contract import Command


def test_brake_rides_in_aux_and_defaults_off():
    c = Command.from_wire({"t": "cmd", "aux": {"brake": True}})
    assert c.brake is True
    assert Command.from_wire({"t": "cmd"}).brake is False
    assert Command(brake=True).to_wire()["aux"]["brake"] is True
