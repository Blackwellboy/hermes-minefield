"""Version 1: no free-text fields, timestamps, content hashes or private names."""

from __future__ import annotations

import json
import re
import uuid

MAX_BYTES = 32768
MAX_CELLS = 128
SCHEMA = "diagnostic_batch.v1"
POLICY = "minefield-fixture.v1"
ENUMS = {
    "origin": {"passive", "synthetic", "user_followup"},
    "observation": {"empty_answer", "tool_no_progress", "request_rejected", "unavailable", "none"},
    "outcome": {"observed", "scoped_clean", "unknown", "skipped"},
    "stack": {"unknown", "custom", "vllm", "llama.cpp", "sglang", "ollama"},
    "model": {"unknown", "custom"},  # public mapping needs a reviewed registry expansion
    "duration": {"unknown", "under_1s", "1_to_10s", "over_10s"},
    "feedback": {"not_tested", "improved", "unchanged"},
    "sampling": {"all_eligible", "bounded_drop"},
}
COUNTS = ("eligible", "inspected", "anomalous", "unavailable", "dropped")
SHAPES = ("answer_present", "reasoning_present", "tools_present", "streaming")
CELL_KEYS = frozenset(ENUMS) | {"counts", "shape"}


class ContractError(ValueError):
    pass


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ContractError("keys")


def validate_cell(cell):
    _keys(cell, CELL_KEYS)
    for name, allowed in ENUMS.items():
        if type(cell[name]) is not str or cell[name] not in allowed:
            raise ContractError("enum")
    _keys(cell["counts"], COUNTS)
    for value in cell["counts"].values():
        if type(value) is not int or not 0 <= value <= 10000:
            raise ContractError("count")
    n = cell["counts"]
    if n["inspected"] + n["unavailable"] + n["dropped"] > n["eligible"] or n["anomalous"] > n["inspected"]:
        raise ContractError("denominator")
    _keys(cell["shape"], SHAPES)
    if any(type(v) is not bool for v in cell["shape"].values()):
        raise ContractError("shape")


def validate(batch):
    _keys(batch, ("schema", "policy", "detector", "registry", "package_id", "cells"))
    if (batch["schema"], batch["policy"], batch["detector"], batch["registry"]) != (
        SCHEMA,
        POLICY,
        "minefield-rules.v1",
        "minefield-0.2.1",
    ):
        raise ContractError("version")
    if type(batch["package_id"]) is not str or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", batch["package_id"]
    ):
        raise ContractError("package_id")
    if type(batch["cells"]) is not list or not 1 <= len(batch["cells"]) <= MAX_CELLS:
        raise ContractError("cells")
    for cell in batch["cells"]:
        validate_cell(cell)
    return batch


def encode(batch):
    validate(batch)
    data = json.dumps(batch, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(data) > MAX_BYTES:
        raise ContractError("size")
    return data


def decode(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ContractError("size")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate_key")
            result[key] = value
        return result

    def constant(value):
        raise ContractError("nonfinite")

    try:
        batch = json.loads(raw.decode("ascii"), object_pairs_hook=pairs, parse_constant=constant)
        return validate(batch)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContractError("invalid_package") from exc


def package(cells):
    return {
        "schema": SCHEMA,
        "policy": POLICY,
        "detector": "minefield-rules.v1",
        "registry": "minefield-0.2.1",
        "package_id": str(uuid.uuid4()),
        "cells": cells,
    }


def project(
    *,
    origin,
    observation,
    outcome,
    stack="unknown",
    duration="unknown",
    feedback="not_tested",
    answer_present=False,
    reasoning_present=False,
    tools_present=False,
    streaming=False,
):
    """Construct from selected finite facts. Never accept an event dict or **extra."""
    unavailable = outcome in {"unknown", "skipped"}
    cell = {
        "origin": origin,
        "observation": observation,
        "outcome": outcome,
        "stack": stack if type(stack) is str and stack in ENUMS["stack"] else "custom",
        "model": "unknown",
        "duration": duration,
        "feedback": feedback,
        "sampling": "all_eligible",
        "counts": {
            "eligible": 1,
            "inspected": int(not unavailable),
            "anomalous": int(outcome == "observed"),
            "unavailable": int(unavailable),
            "dropped": 0,
        },
        "shape": {
            "answer_present": answer_present,
            "reasoning_present": reasoning_present,
            "tools_present": tools_present,
            "streaming": streaming,
        },
    }
    validate_cell(cell)
    return cell
