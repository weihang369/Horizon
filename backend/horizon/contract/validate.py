"""Validation against `schema.json` (design D1): the one wire schema, generated from the frontend's zod contract.

`ContractSchema.check(def_name, value)` validates a value against `#/$defs/<def_name>` with Draft 2020-12.
Validators are compiled once per definition. `errors()` returns readable messages instead of raising.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"


class ContractError(ValueError):
    def __init__(self, def_name: str, problems: list[str]) -> None:
        super().__init__(f"{def_name}: " + "; ".join(problems[:5]))
        self.def_name = def_name
        self.problems = problems


class ContractSchema:
    def __init__(self, path: Path = SCHEMA_PATH) -> None:
        self.doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self.defs: dict[str, Any] = self.doc["$defs"]
        self._validators: dict[str, Draft202012Validator] = {}

    def has(self, def_name: str) -> bool:
        return def_name in self.defs

    def _validator(self, def_name: str) -> Draft202012Validator:
        v = self._validators.get(def_name)
        if v is None:
            if def_name not in self.defs:
                raise KeyError(f"schema.json has no $def {def_name!r}")
            root = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": self.defs,
                    "$ref": f"#/$defs/{def_name}"}
            v = Draft202012Validator(root, format_checker=FormatChecker())
            self._validators[def_name] = v
        return v

    def errors(self, def_name: str, value: Any) -> list[str]:
        out = []
        for e in self._validator(def_name).iter_errors(value):
            where = "/".join(str(p) for p in e.absolute_path) or "(root)"
            out.append(f"{where}: {e.message}")
        return out

    def check(self, def_name: str, value: Any) -> None:
        problems = self.errors(def_name, value)
        if problems:
            raise ContractError(def_name, problems)


@cache
def default_schema() -> ContractSchema:
    return ContractSchema()
