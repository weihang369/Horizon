"""The manual scripts (paid live checks, real Docling conversions): run on purpose, never by a normal `pytest`."""

from horizon.tracing import guard_env

guard_env()   # as in tests/: the tracing switches stay off unless opted in
