"""Home Assistant's event entities, as Turzi events (turzi-apps D56, STACK_AUTOMATIONS.md §8a.4).

An intercom's event entity says what happened at a door in its vendor's words,
and with who did it: Akuvox's ``username``/``user_id``, Hikvision's
``card_no``/``employee_no``/``name``. Turzi needs only that a door rang, opened
or refused, and how; never by whom (Santiago, 2026-10-18). So an event entity
leaves Home Assistant only translated, and with nothing but the translation:

- ``ring``: a doorbell pressed;
- ``access_granted`` / ``access_denied``, with ``method`` (``pin``, ``tag``,
  ``face``, ``qr``, ``fingerprint``);
- ``door_forced``: a door opened without a valid opening.

Anything else an event entity says is not published at all.
"""

from __future__ import annotations

from typing import Any

TURZI_EVENT_TYPES = ["ring", "access_granted", "access_denied", "door_forced"]

# (vendor event type) -> (Turzi event type, method or None)
_VENDOR: dict[str, tuple[str, str | None]] = {
    # Akuvox (homeassistant-local-akuvox, event.py ALL_ACCESS_EVENT_TYPES)
    "valid_code": ("access_granted", "pin"),
    "invalid_code": ("access_denied", "pin"),
    "valid_card": ("access_granted", "tag"),
    "invalid_card": ("access_denied", "tag"),
    "valid_face": ("access_granted", "face"),
    "invalid_face": ("access_denied", "face"),
    "valid_qr": ("access_granted", "qr"),
    "invalid_qr": ("access_denied", "qr"),
    # Hikvision (ha-hikvision-doorbell-integration, isapi/events.py)
    "card_valid": ("access_granted", "tag"),
    "card_no_right": ("access_denied", "tag"),
    "card_invalid_period": ("access_denied", "tag"),
    "card_expired": ("access_denied", "tag"),
    "card_invalid": ("access_denied", "tag"),
    "face_valid": ("access_granted", "face"),
    "face_invalid": ("access_denied", "face"),
    "face_not_exist": ("access_denied", "face"),
    "fingerprint_valid": ("access_granted", "fingerprint"),
    "fingerprint_invalid": ("access_denied", "fingerprint"),
    "door_unlocked_by_public_password": ("access_granted", "pin"),
    "doorbell_ringing": ("ring", None),
    "door_open_abnormal": ("door_forced", None),
}

# Home Assistant's own doorbell event entities (device class doorbell) fire
# `ring` already, or vendor words for it.
_DOORBELL_TYPES = {"ring", "pressed", "button_pressed", "doorbell", "doorbell_ringing"}


def turzi_event(attributes: dict[str, Any]) -> dict[str, Any] | None:
    """The attributes an event entity is published with, or None not to publish it.

    Built from scratch, never by filtering the entity's own attributes, so a
    vendor field added next year cannot leave the building by accident.
    """
    event_type = attributes.get("event_type")
    device_class = attributes.get("device_class")
    if not isinstance(event_type, str):
        return None
    if device_class == "doorbell" and event_type in _DOORBELL_TYPES:
        mapped: tuple[str, str | None] | None = ("ring", None)
    else:
        mapped = _VENDOR.get(event_type)
    if mapped is None:
        return None
    turzi_type, method = mapped
    out: dict[str, Any] = {"event_type": turzi_type, "event_types": list(TURZI_EVENT_TYPES)}
    if device_class == "doorbell" or turzi_type == "ring":
        out["device_class"] = "doorbell"
    if method:
        out["method"] = method
    return out
