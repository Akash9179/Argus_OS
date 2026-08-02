import sys
sys.path.insert(0, "link/gen/python")
from link.v1 import ontology_pb2 as o, messages_pb2 as m
from google.protobuf import timestamp_pb2

hb = m.Heartbeat(link_version=1, ontology_version=1, asset_id="01J0000000000000000000ASSET",
                 asset_class="ugv", status=o.ASSET_STATUS_ACTIVE, battery_fraction=0.87,
                 position=o.Position(latitude_deg=51.5, longitude_deg=-0.12),
                 current_task_id="")
obs = m.ObservationReport(link_version=1, ontology_version=1,
    observation=o.Observation(observation_id="01OBS", entity_id="01ENT", asset_id="01AST",
        position=o.Position(latitude_deg=51.5, longitude_deg=-0.12, altitude_m=12.0),
        confidence=0.4, entity_class="person",
        attributes={"color": "red"}, narration="possible person, low confidence"))
task = m.TaskAssignment(link_version=1, ontology_version=1,
    task=o.Task(task_id="01TSK", asset_id="01AST", task_type="navigate",
        parameters=o.TaskParameters(waypoints=[o.Position(latitude_deg=51.6, longitude_deg=-0.1)]),
        priority=1, status=o.TASK_STATE_PENDING,
        issued_by=o.Issuer(principal_id="operator-1", channel="map")))
ts = m.TaskStatusUpdate(link_version=1, ontology_version=1, task_id="01TSK",
                        status=o.TASK_STATE_RUNNING, progress=0.5, eta_sec=42,
                        message="heading to gate 3")
tel = m.Telemetry(link_version=1, ontology_version=1, asset_id="01AST",
                  position=o.Position(latitude_deg=51.5, longitude_deg=-0.12),
                  heading_deg=270.0, speed_mps=3.2)

for msg in (hb, obs, task, ts, tel):
    data = msg.SerializeToString()
    clone = type(msg)(); clone.ParseFromString(data)
    assert clone == msg, type(msg).__name__
print("round-trip OK for all five messages")

# Open-enum passthrough: an unknown future enum value must survive
ts2 = m.TaskStatusUpdate(link_version=1, ontology_version=1, task_id="01TSK", status=99)
reparsed = m.TaskStatusUpdate(); reparsed.ParseFromString(ts2.SerializeToString())
assert reparsed.status == 99, "unknown enum value dropped"
print("unknown enum value 99 preserved through serialize/parse")

# Open string vocabularies pass through trivially
e = o.Entity(entity_id="01E", entity_class="submarine")  # future domain subtype
e2 = o.Entity(); e2.ParseFromString(e.SerializeToString())
assert e2.entity_class == "submarine"
print("unknown open-vocabulary string preserved")

# battery_fraction is optional: absent (no battery) is distinct from 0.0 (empty)
hb_nobatt = m.Heartbeat(link_version=1, ontology_version=1, asset_id="01FXS", asset_class="fixed_sensor")
hb2 = m.Heartbeat(); hb2.ParseFromString(hb_nobatt.SerializeToString())
assert not hb2.HasField("battery_fraction")
hb_empty = m.Heartbeat(battery_fraction=0.0)
assert hb_empty.HasField("battery_fraction")
print("absent battery distinct from empty battery")

# JSON mapping is mechanical (ISO 8601 timestamps in JSON form)
from google.protobuf import json_format
t = timestamp_pb2.Timestamp(); t.FromJsonString("2026-08-02T12:00:00Z")
hb.timestamp.CopyFrom(t)
j = json_format.MessageToJson(hb)
assert "2026-08-02T12:00:00Z" in j
print("JSON mapping OK, timestamps render as ISO 8601 UTC")
