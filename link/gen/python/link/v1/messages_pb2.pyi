import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from link.v1 import ontology_pb2 as _ontology_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Heartbeat(_message.Message):
    __slots__ = ("link_version", "ontology_version", "asset_id", "asset_class", "status", "battery_fraction", "position", "current_task_id", "timestamp")
    LINK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONTOLOGY_VERSION_FIELD_NUMBER: _ClassVar[int]
    ASSET_ID_FIELD_NUMBER: _ClassVar[int]
    ASSET_CLASS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    BATTERY_FRACTION_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    link_version: int
    ontology_version: int
    asset_id: str
    asset_class: str
    status: _ontology_pb2.AssetStatus
    battery_fraction: float
    position: _ontology_pb2.Position
    current_task_id: str
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, link_version: _Optional[int] = ..., ontology_version: _Optional[int] = ..., asset_id: _Optional[str] = ..., asset_class: _Optional[str] = ..., status: _Optional[_Union[_ontology_pb2.AssetStatus, str]] = ..., battery_fraction: _Optional[float] = ..., position: _Optional[_Union[_ontology_pb2.Position, _Mapping]] = ..., current_task_id: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Telemetry(_message.Message):
    __slots__ = ("link_version", "ontology_version", "asset_id", "position", "heading_deg", "speed_mps", "payload", "timestamp")
    LINK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONTOLOGY_VERSION_FIELD_NUMBER: _ClassVar[int]
    ASSET_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    HEADING_DEG_FIELD_NUMBER: _ClassVar[int]
    SPEED_MPS_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    link_version: int
    ontology_version: int
    asset_id: str
    position: _ontology_pb2.Position
    heading_deg: float
    speed_mps: float
    payload: _struct_pb2.Struct
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, link_version: _Optional[int] = ..., ontology_version: _Optional[int] = ..., asset_id: _Optional[str] = ..., position: _Optional[_Union[_ontology_pb2.Position, _Mapping]] = ..., heading_deg: _Optional[float] = ..., speed_mps: _Optional[float] = ..., payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ObservationReport(_message.Message):
    __slots__ = ("link_version", "ontology_version", "observation")
    LINK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONTOLOGY_VERSION_FIELD_NUMBER: _ClassVar[int]
    OBSERVATION_FIELD_NUMBER: _ClassVar[int]
    link_version: int
    ontology_version: int
    observation: _ontology_pb2.Observation
    def __init__(self, link_version: _Optional[int] = ..., ontology_version: _Optional[int] = ..., observation: _Optional[_Union[_ontology_pb2.Observation, _Mapping]] = ...) -> None: ...

class TaskAssignment(_message.Message):
    __slots__ = ("link_version", "ontology_version", "task", "timestamp")
    LINK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONTOLOGY_VERSION_FIELD_NUMBER: _ClassVar[int]
    TASK_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    link_version: int
    ontology_version: int
    task: _ontology_pb2.Task
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, link_version: _Optional[int] = ..., ontology_version: _Optional[int] = ..., task: _Optional[_Union[_ontology_pb2.Task, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TaskStatusUpdate(_message.Message):
    __slots__ = ("link_version", "ontology_version", "task_id", "status", "progress", "eta_sec", "message", "timestamp")
    LINK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONTOLOGY_VERSION_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    ETA_SEC_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    link_version: int
    ontology_version: int
    task_id: str
    status: _ontology_pb2.TaskState
    progress: float
    eta_sec: int
    message: str
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, link_version: _Optional[int] = ..., ontology_version: _Optional[int] = ..., task_id: _Optional[str] = ..., status: _Optional[_Union[_ontology_pb2.TaskState, str]] = ..., progress: _Optional[float] = ..., eta_sec: _Optional[int] = ..., message: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
