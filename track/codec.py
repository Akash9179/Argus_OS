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


def task_to_dict(task: Message, phrase: str, ordered_by: str = "", reason: str = "") -> dict:
    """A task as applications see it, carrying what was ordered in words.

    The task type is contract vocabulary. Turning it into a sentence is the
    server's job, from its language file, so that an order added after this
    build shipped still reads as English rather than as a code word.

    `ordered_by` is the name of whoever issued it, empty when the record
    names nobody. An application that wants to say who ordered something has
    to be able to do it without reading `issued_by.principal_id`, which is
    an identifier and not for operators.

    `reason` is why the machine is doing this, already a phrase. Composed
    here for the same reason the name is: an application working it out from
    a channel code would attribute orders to the wrong people.
    """
    data = to_dict(task)
    data["phrase"] = phrase
    data["ordered_by"] = ordered_by
    data["reason"] = reason
    return data


def tasks_to_dicts(tasks, view) -> list[dict]:
    """Every order, as `view` renders one."""
    return [view(t) for t in tasks]


def track_to_dict(track: Message, display_name: str, place: str) -> dict:
    """A contact as applications see it, carrying what to call it and where.

    Same reasoning as asset naming. The hedge in "Possible person" is part
    of the honesty law, and an application assembling that name out of an
    entity class and a confidence number would be free to drop it.

    `place` is empty when the contact is in no known zone, so an application
    can say nothing rather than invent somewhere.
    """
    data = to_dict(track)
    data["display_name"] = display_name
    data["place"] = place
    return data


def tracks_to_dicts(tracks, language, class_of, place_of) -> list[dict]:
    """Every contact, named and placed.

    `class_of` takes a track and returns the class of the thing it follows.
    `place_of` takes a position and returns a zone name, or the empty string
    when the position is in no zone we know. Both are passed in rather than
    imported, so this module goes on knowing nothing about entities or zones.
    """
    return [
        track_to_dict(
            t,
            language.track_name(class_of(t), t.confidence),
            language.place_phrase(place_of(t.position)),
        )
        for t in tracks
    ]
