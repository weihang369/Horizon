"""Builds `evals/summary/items.jsonl`, the `summary` suite's 40 dropped-history inputs (docs/ai/05 X10; doc 02 B2;
persona-context design D28, task 9.6). Deterministic: re-running writes the same file, and a test pins its splits.

Each item is a stretch of a chat that a drop would fold: user lines and character replies in English, Malay, Chinese
or a mix, with **3 planted facts** about the user and **1 promise** made by a named speaker, spread through ordinary
small talk. The planted strings are what the five summary judges check: kept fact, kept promise, the promiser named,
same language as most lines, nothing unsupported.

    python evals/summary/build.py
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "items.jsonl"

CHARS = {"wld_seedMeridian": ["Amara", "Mei", "Victor"], "wld_seedSunnyHollow": ["Hana", "Rin", "Takeshi"]}
USER = "Kai"

FACTS = {
    "en": [("works night shifts at a bakery", "I work night shifts at a bakery, so I sleep till noon."),
           ("has a cat called Biscuit", "My cat Biscuit knocked my phone off the table again."),
           ("sister is getting married in June", "My sister's getting married in June and I'm the one giving a speech."),
           ("is learning the cello", "I started cello lessons last month. My neighbours hate me."),
           ("is allergic to peanuts", "Careful with the satay, I'm allergic to peanuts."),
           ("moved from Penang last year", "I only moved here from Penang last year."),
           ("is training for a 10k run", "I'm training for a 10k in October, four runs a week."),
           ("hates coriander", "I can't stand coriander, it tastes like soap to me."),
           ("is saving for a motorbike", "I'm saving every month for a secondhand motorbike."),
           ("grandmother turns 90 next week", "My grandmother turns ninety next week.")],
    "ms": [("bekerja syif malam di kedai roti", "Saya kerja syif malam kat kedai roti, jadi tidur sampai tengah hari."),
           ("ada kucing bernama Biskut", "Kucing saya, Biskut, jatuhkan telefon saya lagi."),
           ("kakak akan berkahwin bulan Jun", "Kakak saya nak kahwin bulan Jun, saya kena beri ucapan."),
           ("sedang belajar biola", "Saya baru mula belajar biola bulan lepas."),
           ("alah kepada kacang", "Hati-hati dengan sate tu, saya alah kacang."),
           ("baru pindah dari Pulau Pinang", "Saya baru pindah dari Pulau Pinang tahun lepas."),
           ("berlatih untuk larian 10 km", "Saya tengah berlatih untuk larian 10 km bulan Oktober."),
           ("tak suka daun ketumbar", "Saya memang tak boleh makan daun ketumbar."),
           ("menyimpan duit untuk motosikal", "Saya simpan duit tiap bulan untuk beli motosikal."),
           ("nenek berumur 90 tahun minggu depan", "Nenek saya genap sembilan puluh tahun minggu depan.")],
    "zh": [("在面包店上夜班", "我在面包店上夜班，所以睡到中午。"),
           ("养了一只叫饼干的猫", "我的猫饼干又把我的手机推到地上了。"),
           ("姐姐六月结婚", "我姐姐六月结婚，我要致辞。"),
           ("正在学大提琴", "我上个月开始学大提琴，邻居都受不了。"),
           ("对花生过敏", "沙爹小心点，我对花生过敏。"),
           ("去年从槟城搬来", "我去年才从槟城搬过来。"),
           ("在为十公里跑步训练", "我在为十月的十公里跑训练，一周跑四次。"),
           ("讨厌香菜", "我受不了香菜，吃起来像肥皂。"),
           ("在存钱买摩托车", "我每个月都在存钱买一辆二手摩托车。"),
           ("奶奶下周满九十岁", "我奶奶下周满九十岁。")],
}
PROMISES = {
    "en": [("send the recipe by Friday", "I'll send you the recipe by Friday, promise."),
           ("check the train times tomorrow", "Leave it with me, I'll check the train times tomorrow."),
           ("bring a book next time", "Next time we talk, I'll bring that book I mentioned.")],
    "ms": [("hantar resipi sebelum Jumaat", "Saya janji hantar resipi tu sebelum Jumaat."),
           ("semak jadual kereta api esok", "Biar saya semak jadual kereta api esok."),
           ("bawa buku itu lain kali", "Lain kali saya bawa buku yang saya sebut tadi.")],
    "zh": [("周五前把食谱发过来", "我周五前把食谱发给你，说好了。"),
           ("明天查火车时刻表", "交给我，我明天查一下火车时刻表。"),
           ("下次带那本书来", "下次聊天我把那本书带来。")],
}
SMALL = {
    "en": ["Morning! Long week.", "Ha, fair enough.", "It rained all day here.", "Did you eat yet?", "Same as always.",
           "That's a good point.", "Anyway, how was your day?", "Not much, honestly."],
    "ms": ["Selamat pagi! Minggu yang panjang.", "Betul juga tu.", "Hujan sepanjang hari kat sini.", "Dah makan?",
           "Macam biasa je.", "Betul cakap awak.", "Hari awak macam mana?", "Tak banyak sangat."],
    "zh": ["早！这周好长。", "哈，也对。", "这里下了一整天的雨。", "吃饭了吗？", "老样子。", "说得有道理。",
           "对了，你今天怎么样？", "其实没什么。"],
}
REPLIES = {
    "en": ["Oh, that sounds like a lot.", "Tell me more about that.", "I'd have done the same.", "Noted."],
    "ms": ["Wah, banyak juga tu.", "Ceritalah lagi.", "Saya pun akan buat sama.", "Baik, saya ingat."],
    "zh": ["哇，听起来事情不少。", "多说一点。", "换我也会这样做。", "记住了。"],
}


def half_splits(ids: list[str]) -> dict[str, str]:
    """X10 asks for 20 dev / 20 test (60 test facts for the 90 % target), not M7's one-third rule for layer-1 and
    layer-2 sets: the half of the ids with the lowest sha256 is `test`. Assigned once and stored on each line; a test
    pins every split, so later items never move an existing one."""
    ranked = sorted(ids, key=lambda i: hashlib.sha256(i.encode()).hexdigest())
    test = set(ranked[:len(ranked) // 2])
    return {i: "test" if i in test else "dev" for i in ids}


def build() -> list[dict[str, object]]:
    rng = random.Random("m8-summary-v1")
    plan = [("en", 10), ("ms", 10), ("zh", 10), ("mix", 10)]
    items: list[dict[str, object]] = []
    for lang, n in plan:
        for k in range(n):
            world = rng.choice(sorted(CHARS))
            cast = CHARS[world]
            speaker = rng.choice(cast)
            # "mix": user lines in Malay; about a third of the replies, and the promise, in English. The summary
            # should follow most lines (counted below): Malay.
            ulang = "ms" if lang == "mix" else lang
            facts = rng.sample(FACTS[ulang], 3)
            promise = rng.choice(PROMISES["en" if lang == "mix" else lang])
            lines: list[dict[str, str]] = []
            langs: list[str] = []

            def reply_lang() -> str:
                return ("en" if rng.random() < 0.35 else "ms") if lang == "mix" else lang
            slots = sorted(rng.sample(range(2, 12), 4))
            fi = 0
            def say(who: str, text: str, tongue: str) -> None:
                lines.append({"speaker": who, "text": text})
                langs.append(tongue)

            for i in range(14):
                if i in slots[:3]:
                    say(USER, facts[fi][1], ulang)
                    fi += 1
                    rl = reply_lang()
                    say(speaker, rng.choice(REPLIES[rl]), rl)
                elif i == slots[3]:
                    say(USER, rng.choice(SMALL[ulang]), ulang)
                    say(speaker, promise[1], "en" if lang == "mix" else lang)
                elif i % 2 == 0:
                    say(USER, rng.choice(SMALL[ulang]), ulang)
                else:
                    rl = reply_lang()
                    say(rng.choice(cast), rng.choice(REPLIES[rl]), rl)
            majority = max(sorted(set(langs)), key=langs.count)
            item_id = f"sum_{lang}_{k + 1:02d}"
            items.append({"id": item_id, "split": "", "language": majority, "world": world,
                          "user": USER, "previous": None, "lines": lines,
                          "facts": [f[0] for f in facts], "promise": {"what": promise[0], "by": speaker}})
    splits = half_splits([str(i["id"]) for i in items])
    return [{**i, "split": splits[str(i["id"])]} for i in items]


def main() -> None:
    items = build()
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8", newline="\n")
    print(f"{len(items)} items -> {OUT}")


if __name__ == "__main__":
    main()
