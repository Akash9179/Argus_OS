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


def asset_to_dict(asset: Message, display_name: str) -> dict:
    """An asset as applications see it, carrying the name to put on screen.

    Naming is resolved here rather than in the application. An application
    that built a name out of asset_class would be reaching below the
    hardware abstraction layer for something it has no business knowing,
    and it would put a second naming authority in the system.
    """
    data = to_dict(asset)
    data["display_name"] = display_name
    return data


def assets_to_dicts(assets, language) -> list[dict]:
    return [asset_to_dict(a, language.asset_name(a)) for a in assets]


def task_to_dict(task: Message, phrase: str) -> dict:
    """A task as applications see it, carrying what was ordered in words.

    The task type is contract vocabulary. Turning it into a sentence is the
    server's job, from its language file, so that an order added after this
    build shipped still reads as English rather than as a code word.
    """
    data = to_dict(task)
    data["phrase"] = phrase
    return data


def tasks_to_dicts(tasks, language) -> list[dict]:
    return [task_to_dict(t, language.task_phrase(t.task_type)) for t in tasks]
