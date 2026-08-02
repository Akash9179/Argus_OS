import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TrackState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRACK_STATE_UNSPECIFIED: _ClassVar[TrackState]
    TRACK_STATE_ACTIVE: _ClassVar[TrackState]
    TRACK_STATE_LOST: _ClassVar[TrackState]
    TRACK_STATE_CLOSED: _ClassVar[TrackState]

class ThreatLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    THREAT_LEVEL_UNSPECIFIED: _ClassVar[ThreatLevel]
    THREAT_LEVEL_NONE: _ClassVar[ThreatLevel]
    THREAT_LEVEL_LOW: _ClassVar[ThreatLevel]
    THREAT_LEVEL_MEDIUM: _ClassVar[ThreatLevel]
    THREAT_LEVEL_HIGH: _ClassVar[ThreatLevel]

class AssetStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ASSET_STATUS_UNSPECIFIED: _ClassVar[AssetStatus]
    ASSET_STATUS_ACTIVE: _ClassVar[AssetStatus]
    ASSET_STATUS_STANDBY: _ClassVar[AssetStatus]
    ASSET_STATUS_FAULT: _ClassVar[AssetStatus]
    ASSET_STATUS_OFFLINE: _ClassVar[AssetStatus]

class TaskState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_STATE_UNSPECIFIED: _ClassVar[TaskState]
    TASK_STATE_PENDING: _ClassVar[TaskState]
    TASK_STATE_ACCEPTED: _ClassVar[TaskState]
    TASK_STATE_RUNNING: _ClassVar[TaskState]
    TASK_STATE_DONE: _ClassVar[TaskState]
    TASK_STATE_FAILED: _ClassVar[TaskState]
    TASK_STATE_CANCELLED: _ClassVar[TaskState]
TRACK_STATE_UNSPECIFIED: TrackState
TRACK_STATE_ACTIVE: TrackState
TRACK_STATE_LOST: TrackState
TRACK_STATE_CLOSED: TrackState
THREAT_LEVEL_UNSPECIFIED: ThreatLevel
THREAT_LEVEL_NONE: ThreatLevel
THREAT_LEVEL_LOW: ThreatLevel
THREAT_LEVEL_MEDIUM: ThreatLevel
THREAT_LEVEL_HIGH: ThreatLevel
ASSET_STATUS_UNSPECIFIED: AssetStatus
ASSET_STATUS_ACTIVE: AssetStatus
ASSET_STATUS_STANDBY: AssetStatus
ASSET_STATUS_FAULT: AssetStatus
ASSET_STATUS_OFFLINE: AssetStatus
TASK_STATE_UNSPECIFIED: TaskState
TASK_STATE_PENDING: TaskState
TASK_STATE_ACCEPTED: TaskState
TASK_STATE_RUNNING: TaskState
TASK_STATE_DONE: TaskState
TASK_STATE_FAILED: TaskState
TASK_STATE_CANCELLED: TaskState

class Position(_message.Message):
    __slots__ = ("latitude_deg", "longitude_deg", "altitude_m")
    LATITUDE_DEG_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_DEG_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_M_FIELD_NUMBER: _ClassVar[int]
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    def __init__(self, latitude_deg: _Optional[float] = ..., longitude_deg: _Optional[float] = ..., altitude_m: _Optional[float] = ...) -> None: ...

class Velocity(_message.Message):
    __slots__ = ("speed_mps", "course_deg", "vertical_mps")
    SPEED_MPS_FIELD_NUMBER: _ClassVar[int]
    COURSE_DEG_FIELD_NUMBER: _ClassVar[int]
    VERTICAL_MPS_FIELD_NUMBER: _ClassVar[int]
    speed_mps: float
    course_deg: float
    vertical_mps: float
    def __init__(self, speed_mps: _Optional[float] = ..., course_deg: _Optional[float] = ..., vertical_mps: _Optional[float] = ...) -> None: ...

class Polygon(_message.Message):
    __slots__ = ("exterior",)
    EXTERIOR_FIELD_NUMBER: _ClassVar[int]
    exterior: _containers.RepeatedCompositeFieldContainer[Position]
    def __init__(self, exterior: _Optional[_Iterable[_Union[Position, _Mapping]]] = ...) -> None: ...

class Entity(_message.Message):
    __slots__ = ("entity_id", "entity_class", "attributes", "first_seen", "last_seen")
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITY_CLASS_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    FIRST_SEEN_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    entity_id: str
    entity_class: str
    attributes: _containers.ScalarMap[str, str]
    first_seen: _timestamp_pb2.Timestamp
    last_seen: _timestamp_pb2.Timestamp
    def __init__(self, entity_id: _Optional[str] = ..., entity_class: _Optional[str] = ..., attributes: _Optional[_Mapping[str, str]] = ..., first_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Observation(_message.Message):
    __slots__ = ("observation_id", "entity_id", "asset_id", "position", "confidence", "entity_class", "attributes", "narration", "timestamp")
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    OBSERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    ASSET_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    ENTITY_CLASS_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    NARRATION_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    observation_id: str
    entity_id: str
    asset_id: str
    position: Position
    confidence: float
    entity_class: str
    attributes: _containers.ScalarMap[str, str]
    narration: str
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, observation_id: _Optional[str] = ..., entity_id: _Optional[str] = ..., asset_id: _Optional[str] = ..., position: _Optional[_Union[Position, _Mapping]] = ..., confidence: _Optional[float] = ..., entity_class: _Optional[str] = ..., attributes: _Optional[_Mapping[str, str]] = ..., narration: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TrackPoint(_message.Message):
    __slots__ = ("timestamp", "position", "velocity")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    VELOCITY_FIELD_NUMBER: _ClassVar[int]
    timestamp: _timestamp_pb2.Timestamp
    position: Position
    velocity: Velocity
    def __init__(self, timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., position: _Optional[_Union[Position, _Mapping]] = ..., velocity: _Optional[_Union[Velocity, _Mapping]] = ...) -> None: ...

class Track(_message.Message):
    __slots__ = ("track_id", "entity_id", "state", "position", "velocity", "threat_level", "confidence", "contributing_asset_ids", "observation_ids", "history")
    TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    VELOCITY_FIELD_NUMBER: _ClassVar[int]
    THREAT_LEVEL_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    CONTRIBUTING_ASSET_IDS_FIELD_NUMBER: _ClassVar[int]
    OBSERVATION_IDS_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    track_id: str
    entity_id: str
    state: TrackState
    position: Position
    velocity: Velocity
    threat_level: ThreatLevel
    confidence: float
    contributing_asset_ids: _containers.RepeatedScalarFieldContainer[str]
    observation_ids: _containers.RepeatedScalarFieldContainer[str]
    history: _containers.RepeatedCompositeFieldContainer[TrackPoint]
    def __init__(self, track_id: _Optional[str] = ..., entity_id: _Optional[str] = ..., state: _Optional[_Union[TrackState, str]] = ..., position: _Optional[_Union[Position, _Mapping]] = ..., velocity: _Optional[_Union[Velocity, _Mapping]] = ..., threat_level: _Optional[_Union[ThreatLevel, str]] = ..., confidence: _Optional[float] = ..., contributing_asset_ids: _Optional[_Iterable[str]] = ..., observation_ids: _Optional[_Iterable[str]] = ..., history: _Optional[_Iterable[_Union[TrackPoint, _Mapping]]] = ...) -> None: ...

class Asset(_message.Message):
    __slots__ = ("asset_id", "asset_class", "capabilities", "status", "position", "battery_fraction", "current_task_id", "last_heartbeat")
    ASSET_ID_FIELD_NUMBER: _ClassVar[int]
    ASSET_CLASS_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    BATTERY_FRACTION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TASK_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    asset_id: str
    asset_class: str
    capabilities: _struct_pb2.Struct
    status: AssetStatus
    position: Position
    battery_fraction: float
    current_task_id: str
    last_heartbeat: _timestamp_pb2.Timestamp
    def __init__(self, asset_id: _Optional[str] = ..., asset_class: _Optional[str] = ..., capabilities: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., status: _Optional[_Union[AssetStatus, str]] = ..., position: _Optional[_Union[Position, _Mapping]] = ..., battery_fraction: _Optional[float] = ..., current_task_id: _Optional[str] = ..., last_heartbeat: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TaskParameters(_message.Message):
    __slots__ = ("waypoints", "target_track_id", "speed_mps", "extras")
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    TARGET_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    SPEED_MPS_FIELD_NUMBER: _ClassVar[int]
    EXTRAS_FIELD_NUMBER: _ClassVar[int]
    waypoints: _containers.RepeatedCompositeFieldContainer[Position]
    target_track_id: str
    speed_mps: float
    extras: _struct_pb2.Struct
    def __init__(self, waypoints: _Optional[_Iterable[_Union[Position, _Mapping]]] = ..., target_track_id: _Optional[str] = ..., speed_mps: _Optional[float] = ..., extras: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class Issuer(_message.Message):
    __slots__ = ("principal_id", "channel")
    PRINCIPAL_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    principal_id: str
    channel: str
    def __init__(self, principal_id: _Optional[str] = ..., channel: _Optional[str] = ...) -> None: ...

class TaskStateChange(_message.Message):
    __slots__ = ("state", "timestamp", "message")
    STATE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    state: TaskState
    timestamp: _timestamp_pb2.Timestamp
    message: str
    def __init__(self, state: _Optional[_Union[TaskState, str]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., message: _Optional[str] = ...) -> None: ...

class Task(_message.Message):
    __slots__ = ("task_id", "asset_id", "task_type", "parameters", "priority", "status", "issued_by", "status_history")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    ASSET_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ISSUED_BY_FIELD_NUMBER: _ClassVar[int]
    STATUS_HISTORY_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    asset_id: str
    task_type: str
    parameters: TaskParameters
    priority: int
    status: TaskState
    issued_by: Issuer
    status_history: _containers.RepeatedCompositeFieldContainer[TaskStateChange]
    def __init__(self, task_id: _Optional[str] = ..., asset_id: _Optional[str] = ..., task_type: _Optional[str] = ..., parameters: _Optional[_Union[TaskParameters, _Mapping]] = ..., priority: _Optional[int] = ..., status: _Optional[_Union[TaskState, str]] = ..., issued_by: _Optional[_Union[Issuer, _Mapping]] = ..., status_history: _Optional[_Iterable[_Union[TaskStateChange, _Mapping]]] = ...) -> None: ...

class ZoneRule(_message.Message):
    __slots__ = ("rule_type", "parameters")
    class ParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    RULE_TYPE_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    rule_type: str
    parameters: _containers.ScalarMap[str, str]
    def __init__(self, rule_type: _Optional[str] = ..., parameters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Zone(_message.Message):
    __slots__ = ("zone_id", "name", "geometry", "zone_type", "rules")
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    GEOMETRY_FIELD_NUMBER: _ClassVar[int]
    ZONE_TYPE_FIELD_NUMBER: _ClassVar[int]
    RULES_FIELD_NUMBER: _ClassVar[int]
    zone_id: str
    name: str
    geometry: Polygon
    zone_type: str
    rules: _containers.RepeatedCompositeFieldContainer[ZoneRule]
    def __init__(self, zone_id: _Optional[str] = ..., name: _Optional[str] = ..., geometry: _Optional[_Union[Polygon, _Mapping]] = ..., zone_type: _Optional[str] = ..., rules: _Optional[_Iterable[_Union[ZoneRule, _Mapping]]] = ...) -> None: ...

class Mission(_message.Message):
    __slots__ = ("mission_id", "name", "objective", "task_ids", "status")
    MISSION_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    OBJECTIVE_FIELD_NUMBER: _ClassVar[int]
    TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    mission_id: str
    name: str
    objective: str
    task_ids: _containers.RepeatedScalarFieldContainer[str]
    status: TaskState
    def __init__(self, mission_id: _Optional[str] = ..., name: _Optional[str] = ..., objective: _Optional[str] = ..., task_ids: _Optional[_Iterable[str]] = ..., status: _Optional[_Union[TaskState, str]] = ...) -> None: ...

class Relationship(_message.Message):
    __slots__ = ("relationship_id", "subject_id", "predicate", "object_id", "confidence", "timestamp")
    RELATIONSHIP_ID_FIELD_NUMBER: _ClassVar[int]
    SUBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PREDICATE_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    relationship_id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, relationship_id: _Optional[str] = ..., subject_id: _Optional[str] = ..., predicate: _Optional[str] = ..., object_id: _Optional[str] = ..., confidence: _Optional[float] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
