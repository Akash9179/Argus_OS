"""Mapping between protobuf objects and the JSON the interfaces serve.

The JSON representation is derived mechanically from the protos rather than
hand-written, so the REST and WebSocket surfaces cannot drift from the
contract. Field names keep their proto spelling (snake_case) for the same
reason.

Note on unknown values: protobuf renders an enum value it does not
recognise as its number rather than dropping the field, and unknown fields
survive in the stored bytes even though JSON cannot show them. Nothing a
newer asset sends is ever destroyed by passing through this layer.
"""

from __future__ import annotations

from google.protobuf import json_format
from google.protobuf.message import Message


def to_dict(message: Message) -> dict:
    """A JSON-ready dictionary for one protobuf message."""
    return json_format.MessageToDict(message, preserving_proto_field_name=True)


def to_dicts(messages) -> list[dict]:
    return [to_dict(m) for m in messages]
