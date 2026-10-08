"""Theme-song audio checks (creation-followups design D6, D-87). Pure functions over bytes, no dependency.

- **Sniff** by content: an MP3 is an optional ID3v2 tag followed by MPEG audio Layer III frames. Two consecutive valid
  frame headers are required, so a stray `FF Ex` byte pair in other data isn't taken for audio.
- **Duration** walks every frame header (CBR or VBR) and sums `samples_per_frame / sample_rate`; None when no frame
  parses. `durationSec` is informational: the player decodes the real length.
- `silent_mp3(frames)` builds a tiny valid clip (MPEG-1 Layer III, 128 kbps, 44.1 kHz, zero payload) for the fake
  provider and the tests, so no real audio is committed.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_SONG_BYTES = 8 * 1024 * 1024        # a 30 s Lyria Clip at 320 kbps is about 1.2 MB
RESYNC_LIMIT = 4096                     # bytes scanned for the next frame after a bad header

_BITRATES_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_BITRATES_V2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}  # version bits → rates


@dataclass(frozen=True)
class Frame:
    length: int
    samples: int
    sample_rate: int


def _frame(data: bytes, i: int) -> Frame | None:
    """The Layer III frame header at `i`, or None."""
    if i + 4 > len(data) or data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
        return None
    version = (data[i + 1] >> 3) & 0x3          # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5, 1 = reserved
    layer = (data[i + 1] >> 1) & 0x3            # 1 = Layer III
    br_idx = data[i + 2] >> 4
    sr_idx = (data[i + 2] >> 2) & 0x3
    padding = (data[i + 2] >> 1) & 0x1
    if version == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:
        return None
    rate = _RATES[version][sr_idx]
    if version == 3:
        kbps, samples, coef = _BITRATES_V1_L3[br_idx], 1152, 144
    else:
        kbps, samples, coef = _BITRATES_V2_L3[br_idx], 576, 72
    length = coef * kbps * 1000 // rate + padding
    return Frame(length=length, samples=samples, sample_rate=rate) if length > 4 else None


def _audio_start(data: bytes) -> int:
    """Skip an ID3v2 tag (its size is syncsafe; a footer adds 10 bytes)."""
    if len(data) >= 10 and data[:3] == b"ID3":
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        return 10 + size + (10 if data[5] & 0x10 else 0)
    return 0


def is_mp3(data: bytes) -> bool:
    i = _audio_start(data)
    first = _frame(data, i)
    if first is None:
        return False
    nxt = i + first.length
    return nxt == len(data) or _frame(data, nxt) is not None


def mp3_duration(data: bytes) -> float | None:
    i, seconds, frames = _audio_start(data), 0.0, 0
    while i < len(data):
        f = _frame(data, i)
        if f is None:
            j = data.find(b"\xff", i + 1, i + RESYNC_LIMIT)
            if j < 0:
                break
            i = j
            continue
        seconds += f.samples / f.sample_rate
        frames += 1
        i += f.length
    return round(seconds, 3) if frames else None


def silent_mp3(frames: int = 8) -> bytes:
    """A valid MP3 of `frames` silent frames (each 417 bytes, 1152 samples at 44.1 kHz ≈ 26 ms)."""
    header = bytes((0xFF, 0xFB, 0x90, 0x00))   # MPEG-1 Layer III, no CRC, 128 kbps, 44.1 kHz, no padding
    return (header + bytes(417 - 4)) * frames
