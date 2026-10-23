"""The reply language cue (persona-context D35, the maintainer's choice after the paid `long` run, 2026-10-12).

The reply rule ("reply in the language the user writes in") sits in the cached system prompt, and against an English
persona, English example lines and an English greeting the model ignored it: Malay user lines got English replies
(`agent` 2 of 75 in Malay, `naive` 0 of 50). So when the latest user line is clearly not English, both engines add one
line at the very end of the request: "Kai wrote in Malay. Reply in Malay."

Detection is code and deliberately cautious: a non-Latin script decides at once; Latin text counts as Malay only when
common Malay words make up a clear share of it. Anything unsure gets no cue (the system rule still applies, and English
is the app's focus). M9's turn plan can hand this to Jev.
"""

from __future__ import annotations

import re

from horizon.ai.contexts import TurnContext

# (name, pattern): the first script with at least 3 letters in the line wins
SCRIPTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Japanese", re.compile(r"[぀-ヿ]")),
    ("Korean", re.compile(r"[가-힯]")),
    ("Chinese", re.compile(r"[一-鿿]")),
    ("Thai", re.compile(r"[฀-๿]")),
    ("Tamil", re.compile(r"[஀-௿]")),
    ("Hindi", re.compile(r"[ऀ-ॿ]")),
    ("Arabic", re.compile(r"[؀-ۿ]")),
    ("Russian", re.compile(r"[Ѐ-ӿ]")),
)
MALAY = frozenset(
    "saya awak aku kamu dia kita kami mereka tak tidak ada dah sudah nak mahu ni ini tu itu dengan untuk yang hari lagi "
    "boleh jangan macam sangat juga apa kenapa mana bila betul baik lah kan pun je jer ke kat dalam dari pada akan "
    "belum masih tengah sedang cuma banyak sikit selalu hujan makan minum kerja rumah kawan cakap tahu".split())
WORD = re.compile(r"[a-zA-Z']+")


def detect_language(text: str) -> str | None:
    """A language name when `text` is clearly not English, else None."""
    for name, pat in SCRIPTS:
        if len(pat.findall(text)) >= 3:
            return name
    words = [w.lower() for w in WORD.findall(text)]
    malay = sum(1 for w in words if w in MALAY)
    if malay >= 2 and malay / max(1, len(words)) >= 0.25:
        return "Malay"
    return None


def language_cue(ctx: TurnContext, *, english: bool = False) -> str | None:
    """The cue for the latest user line in the window, if it is clearly not English. With `english` (the agent engine,
    U-84), an English or unsure line gets "Reply in English." too: on 23 Oct a group reply to a plain English question
    came back in Chinese with only the system rule to go on (M10's recaps did the same; unsure counts as English)."""
    latest = next((m.content for m in reversed(ctx.session.recent) if m.author_type == "user" and m.content), "")
    lang = detect_language(latest) if latest else None
    if lang is None:
        if not (english and WORD.search(latest)):
            return None
        lang = "English"
    you = str((ctx.session.world.you or {}).get("displayName") or "The user")
    return f"{you} wrote in {lang}. Reply in {lang}."
