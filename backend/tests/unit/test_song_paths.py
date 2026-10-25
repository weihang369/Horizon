"""Theme-song file names (creation-followups task 3.2, design D6): a new immutable name per version and format."""

from __future__ import annotations

from horizon.services import assets


def test_song_names_carry_version_and_format() -> None:
    assert assets.song_rel("wld_a", "chr_b", 3) == "gen/wld_a/chr_b/song_v3.proc.json"
    assert assets.song_rel("wld_a", "chr_b", 4, "mp3") == "gen/wld_a/chr_b/song_v4.mp3"
    assert assets.original_rel("wld_a", "chr_b", "task_x", 1, "mp3") == "originals/wld_a/chr_b/task_x_a1.mp3"
