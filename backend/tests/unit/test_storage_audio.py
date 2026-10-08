"""Theme-song audio checks (creation-followups task 3.1, design D6). In-code stubs only: no audio file is committed."""

from __future__ import annotations

from horizon.storage.audio import MAX_SONG_BYTES, is_mp3, mp3_duration, silent_mp3

FRAME_S = 1152 / 44100


def id3(payload: bytes = b"TIT2" + bytes(20)) -> bytes:
    n = len(payload)
    size = bytes(((n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F))   # syncsafe
    return b"ID3\x04\x00\x00" + size + payload


def test_bare_frames_are_mp3_with_their_duration() -> None:
    clip = silent_mp3(10)
    assert is_mp3(clip)
    assert mp3_duration(clip) == round(10 * FRAME_S, 3)


def test_id3_tag_is_skipped() -> None:
    clip = id3() + silent_mp3(5)
    assert is_mp3(clip)
    assert mp3_duration(clip) == round(5 * FRAME_S, 3)


def test_mpeg2_frames_count_576_samples() -> None:
    # MPEG-2 Layer III, 64 kbps, 24 kHz: header FF F3 84 00 → 72 * 64000 / 24000 = 192 bytes per frame
    frame = bytes((0xFF, 0xF3, 0x84, 0x00)) + bytes(192 - 4)
    assert is_mp3(frame * 3)
    assert mp3_duration(frame * 3) == round(3 * 576 / 24000, 3)


def test_junk_between_frames_is_skipped() -> None:
    clip = silent_mp3(2) + b"\x00junk\x00" + silent_mp3(2)
    assert mp3_duration(clip) == round(4 * FRAME_S, 3)


def test_other_bytes_are_not_mp3() -> None:
    png = b"\x89PNG\r\n\x1a\n" + bytes(64)
    wav = b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(64)
    for data in (png, wav, b"", b"\xff\xfb", bytes(1000)):
        assert not is_mp3(data)
        assert mp3_duration(data) is None
    assert not is_mp3(b"\xff\xfb\x90\x00" + bytes(100))   # one header, then no second frame where it should be


def test_size_cap_is_well_above_a_clip() -> None:
    thirty_seconds_at_320k = 30 * 320_000 // 8
    assert MAX_SONG_BYTES > 6 * thirty_seconds_at_320k
