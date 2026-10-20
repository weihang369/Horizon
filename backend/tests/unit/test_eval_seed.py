"""The evals' frozen seed (v1 test stage): `evals/seed-v0` is `seed/` at 36b51f4, the content every eval set was labelled
on, so recording the shipped demo for real never moves a gold span or a stored request body. Its configuration must
follow the repo's own seed, or the evals would price and route differently from the app."""

from __future__ import annotations

import json

import pytest

from horizon.config import REPO_ROOT
from horizon.evals.runner import EVAL_SEED


@pytest.mark.parametrize("name", ["pricing.json", "settings.json", "runtime.json"])
def test_the_frozen_seed_follows_the_repo_config(name: str) -> None:
    ours = json.loads((EVAL_SEED / name).read_text(encoding="utf-8"))
    repo = json.loads((REPO_ROOT / "seed" / name).read_text(encoding="utf-8"))
    assert ours == repo, f"copy seed/{name} to evals/seed-v0/{name}"


def test_the_frozen_seed_keeps_the_labelled_pieces() -> None:
    from horizon.evals import retrieval as R

    assert {"kch_hanaRecipe05", "kch_amaraTri01"} <= set(R.seed_chunks())
