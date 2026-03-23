import json
from typing import Any

from ghunt.objects.encoders import GHuntEncoder


def serialize(obj: Any) -> Any:
    """
    Serializes any GHunt object (or plain Python object) into a
    JSON-compatible dict/list/primitive using GHuntEncoder.

    This handles:
    - datetime -> formatted string
    - set -> list
    - SmartObj subclasses (with __dict__) -> dict
    - Autoslot objects (with __slots__) -> dict
    """
    raw = json.dumps(obj, cls=GHuntEncoder)
    return json.loads(raw)


def safe_serialize(obj: Any) -> Any:
    """
    Same as serialize() but catches errors and returns a string fallback.
    """
    try:
        return serialize(obj)
    except Exception as e:
        return {"_serialization_error": str(e), "_repr": repr(obj)}
