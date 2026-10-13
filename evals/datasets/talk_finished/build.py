"""Build `talk_finished.jsonl`: "is the talk finished?" over watch scenes (group-watch D14, D23; doc 07 G7; doc 02 B5;
evaluation-harness "M10 decision sets").

Run from backend/: `uv run python ../evals/datasets/talk_finished/build.py`. Deterministic. Labels were written blind
under `evals/reviews/m10-labels.md` (committed first), before any Jev answer.

Each item is a watch scene's last few lines under a premise, with the state built by the live code exactly as a
planned scene turn asks it (`state_input` for a `scene` cast request: the premise, the earlier lines, and the last line
as `quoted_latest`). `yes` means the thread has stopped moving (goodbye loops, polite agreement, the same point again);
`no` means something is still open or moving, including a scene right after a director's note. The label is the noul's
answer: the run scores p against the `t_end` chosen on dev.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals" / "datasets" / "who_speaks"))

from build import USER, WHO, WORLDS, id_prefix, profiles, views  # noqa: E402

from horizon.ai.agent.cast_plan import state_input  # noqa: E402
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.contexts import CastRequest, MessageView, ParticipantView, SessionContext, WorldView  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

T0 = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)
PREMISES = {
    "clinic": ("m", "A late council session runs past midnight over the night clinic's budget."),
    "powercut": ("m", "Three old friends wait out a power cut in a hospital cafeteria."),
    "games": ("m", "A live radio debate on whether the city should bid to host the Games."),
    "storm": ("s", "A storm traps the family in the flower shop overnight."),
    "party": ("s", "The family secretly plans Takeshi's retirement party in the kitchen."),
    "launch": ("s", "Rin's game launches tonight and the servers keep wobbling."),
}
NOTE = "note"   # a director's note line: posted by the user as a `direction` message
Line = tuple[str, str]

# (premise, lines, label, lang)
SCENES: list[tuple[str, list[Line], str, str]] = [
    # ── yes: goodbye and good-night loops ──
    ("clinic", [("victor", "Then we adjourn. Good night, colleagues."), ("mei", "Good night, Victor."),
                ("amara", "Night, both of you. Drive safe."), ("victor", "And you. Good night.")], "yes", "en"),
    ("powercut", [("mei", "The lights are back. I'm heading home."), ("amara", "Same. Take care, Mei."),
                  ("mei", "You too. See you Thursday."), ("victor", "Goodbye, then. Thursday.")], "yes", "en"),
    ("storm", [("hana", "Okay, I'm going to sleep now. Night night!"), ("rin", "Night."),
               ("takeshi", "Good night, girls."), ("hana", "Night, Dad! Night, Rin!")], "yes", "en"),
    ("party", [("rin", "Right, I'm off. Don't tell Dad anything."), ("hana", "Bye, Rin! See you tomorrow!"),
               ("rin", "Bye."), ("hana", "Bye bye!")], "yes", "en"),
    ("launch", [("takeshi", "It's late. I'm turning in. Good luck tonight."), ("rin", "Thanks. Night, Dad."),
                ("hana", "Night, Dad!"), ("takeshi", "Good night, both.")], "yes", "en"),
    ("games", [("victor", "And that's our time. Thank you both."), ("mei", "Thank you, Victor."),
               ("amara", "Thanks for having us."), ("victor", "Thank you, and good night to our listeners.")],
     "yes", "en"),
    ("clinic", [("amara", "I'll see you all at the next session, then."), ("mei", "See you then."),
                ("victor", "Until then."), ("amara", "Bye for now.")], "yes", "en"),
    ("powercut", [("victor", "I'll leave you two to it. Good evening."), ("amara", "Evening, Victor."),
                  ("mei", "Bye, Victor."), ("victor", "Goodbye, goodbye.")], "yes", "en"),
    ("storm", [("takeshi", "Lights out, everyone. Sleep well."), ("hana", "Sleep well, Dad."),
               ("rin", "Yeah, night."), ("takeshi", "Night.")], "yes", "en"),
    ("party", [("hana", "I have to open the shop early. Bye, everyone!"), ("takeshi", "Bye, Hana."),
               ("rin", "Later."), ("hana", "Bye! Love you all!")], "yes", "en"),
    ("launch", [("hana", "Okay, I'm logging off! Good night!"), ("rin", "Night, sis."), ("hana", "Night night!"),
                ("rin", "Go to sleep, Hana.")], "yes", "en"),
    ("games", [("mei", "I need to catch my train. Lovely talking."), ("amara", "You too, Mei. Safe trip."),
               ("mei", "Thanks. Bye."), ("amara", "Bye!")], "yes", "en"),
    # ── yes: polite agreement loops ──
    ("clinic", [("mei", "So we keep the clinic open three nights a week."), ("amara", "Agreed, three nights."),
                ("victor", "Agreed."), ("mei", "Good, we all agree then.")], "yes", "en"),
    ("powercut", [("amara", "This is a nice way to spend a blackout, honestly."), ("mei", "It really is."),
                  ("victor", "Quite right, quite right."), ("amara", "Really nice.")], "yes", "en"),
    ("storm", [("hana", "We're so lucky to be together tonight."), ("takeshi", "Very lucky."),
               ("rin", "Yeah. Lucky."), ("hana", "So lucky!")], "yes", "en"),
    ("party", [("rin", "So, cake from the bakery downstairs."), ("hana", "Yes! The bakery!"),
               ("takeshi", "The bakery is good."), ("rin", "Bakery it is, then.")], "yes", "en"),
    ("launch", [("hana", "Your game looks amazing, Rin."), ("takeshi", "It does. Amazing."),
                ("hana", "Really amazing!"), ("takeshi", "Truly.")], "yes", "en"),
    ("games", [("amara", "Whatever we decide, it has to be honest with the public."), ("mei", "Absolutely."),
               ("victor", "Couldn't agree more."), ("amara", "Yes, completely.")], "yes", "en"),
    ("clinic", [("victor", "Fair enough, Amara, you've made your case."), ("amara", "Thank you, Victor."),
                ("mei", "It was a good case."), ("victor", "A very good case indeed.")], "yes", "en"),
    ("powercut", [("mei", "Cheers to small mercies and vending machines."), ("amara", "Cheers!"),
                  ("victor", "Cheers."), ("mei", "Cheers, cheers.")], "yes", "en"),
    ("storm", [("rin", "Okay, the candles were a good idea, Dad."), ("takeshi", "Thank you, Rin."),
               ("hana", "Such a good idea!"), ("rin", "Yeah. Good idea.")], "yes", "en"),
    ("party", [("takeshi", "I don't know what you're whispering about, but it sounds nice."), ("hana", "It's nothing!"),
               ("rin", "Nothing, Dad."), ("hana", "Totally nothing!")], "yes", "en"),
    ("launch", [("rin", "Okay, the servers are fine now. Finally."), ("hana", "Yay, fine!"),
                ("takeshi", "Good. Fine is good."), ("rin", "Yep. Fine.")], "yes", "en"),
    ("games", [("victor", "On that, at least, we're united."), ("mei", "United, yes."), ("amara", "Fully united."),
               ("victor", "How refreshing.")], "yes", "en"),
    ("clinic", [("amara", "Thanks, everyone. That was productive."), ("mei", "It was, thank you."),
                ("victor", "Thank you all."), ("amara", "Thanks again.")], "yes", "en"),
    ("powercut", [("victor", "Well, that was a lovely chat."), ("amara", "It was lovely."), ("mei", "Very lovely."),
                  ("victor", "Lovely, lovely.")], "yes", "en"),
    # ── yes: the same point again, or nothing left open ──
    ("clinic", [("mei", "The numbers don't support a fourth night."),
                ("victor", "As Mei says, the numbers don't support it."),
                ("mei", "Exactly, there's no money for a fourth night."),
                ("amara", "Right, no fourth night, the money isn't there.")], "yes", "en"),
    ("powercut", [("amara", "I'm just glad nobody was hurt."), ("mei", "Yes, the main thing is nobody's hurt."),
                  ("victor", "Indeed, no harm done to anyone."), ("amara", "Nobody hurt. That's what counts.")],
     "yes", "en"),
    ("storm", [("takeshi", "The roof will hold. It's held for thirty years."), ("hana", "It'll hold, Dad's right."),
               ("rin", "Yeah, it'll hold."), ("takeshi", "Thirty years. It'll hold.")], "yes", "en"),
    ("party", [("hana", "He'll love it, I just know it."), ("rin", "He'll love it."),
               ("hana", "He's going to love it so much!"), ("rin", "We get it. He'll love it.")], "yes", "en"),
    ("launch", [("rin", "Launch went fine. People are playing."), ("hana", "People are playing it!"),
                ("takeshi", "So people are playing it."), ("rin", "Yes, Dad. People are playing it.")], "yes", "en"),
    ("games", [("mei", "The cost overruns are the real problem."), ("amara", "Overruns, yes, that's the issue."),
               ("victor", "The overruns, as Mei keeps saying."), ("mei", "Because it's true. Overruns.")],
     "yes", "en"),
    ("clinic", [("victor", "I concede. You win this round."), ("amara", "Thank you."),
                ("mei", "Fair concession."), ("victor", "Nothing more to add.")], "yes", "en"),
    ("powercut", [("mei", "So, nothing to do but wait."), ("amara", "Nothing to do but wait."),
                  ("victor", "We wait."), ("mei", "Yep. We wait.")], "yes", "en"),
    ("storm", [("hana", "I guess we just listen to the rain now."), ("rin", "Guess so."),
               ("takeshi", "Mm."), ("hana", "Just the rain.")], "yes", "en"),
    ("party", [("takeshi", "Whatever you two are planning, I'm sure it's fine."), ("rin", "It's fine."),
               ("hana", "Totally fine!"), ("takeshi", "Fine, then.")], "yes", "en"),
    ("launch", [("hana", "So we just wait for the reviews?"), ("rin", "We just wait."),
                ("takeshi", "Waiting is fine."), ("hana", "Okay, waiting!")], "yes", "en"),
    ("games", [("amara", "I've said all I can say on that."), ("mei", "Same here."),
               ("victor", "And I have rested my case."), ("amara", "Then I think we're done.")], "yes", "en"),
    ("clinic", [("mei", "Motion carried."), ("victor", "Carried."), ("amara", "Carried, yes."),
                ("mei", "Then that's settled.")], "yes", "en"),
    ("powercut", [("amara", "Honestly, I'm out of things to say."), ("victor", "A rare silence."),
                  ("mei", "I'll enjoy it."), ("amara", "Mm.")], "yes", "en"),
    ("storm", [("rin", "Okay, I've told every story I know."), ("hana", "Me too."),
               ("takeshi", "I've told mine twice."), ("rin", "Three times, Dad.")], "yes", "en"),
    ("party", [("hana", "Balloons, cake, the old photos. That's everything."), ("rin", "That's everything."),
               ("hana", "We've got everything!"), ("rin", "We do.")], "yes", "en"),
    ("launch", [("rin", "Patch is out. Nothing else to fix tonight."), ("hana", "Nothing else? Yay!"),
                ("takeshi", "Then rest."), ("rin", "Yeah. Done.")], "yes", "en"),
    ("games", [("victor", "We're going in circles."), ("mei", "We are."), ("amara", "Round and round."),
               ("victor", "Indeed. Circles.")], "yes", "en"),
    ("clinic", [("amara", "Thank you for listening."), ("victor", "Thank you for speaking."),
                ("amara", "Thank you for letting me."), ("victor", "Thank you, truly.")], "yes", "en"),
    ("storm", [("takeshi", "Sorry the shop is so cold."), ("hana", "It's fine, Dad!"), ("rin", "It's fine."),
               ("takeshi", "Sorry anyway.")], "yes", "en"),
    ("party", [("rin", "Sorry I snapped earlier."), ("hana", "It's okay!"), ("rin", "No, really, sorry."),
               ("hana", "It's really okay, Rin!")], "yes", "en"),
    ("launch", [("takeshi", "I'm proud of you, Rin."), ("rin", "Thanks, Dad."), ("takeshi", "Very proud."),
                ("rin", "I know. Thanks.")], "yes", "en"),
    ("games", [("mei", "Good debate, everyone."), ("amara", "Good debate."), ("victor", "A fine debate."),
               ("mei", "Really good.")], "yes", "en"),
    ("powercut", [("victor", "Well. Shall we just sit?"), ("mei", "Let's just sit."), ("amara", "Sitting."),
                  ("victor", "Sitting it is.")], "yes", "en"),
    ("clinic", [("mei", "I think we've covered it."), ("amara", "We have."), ("victor", "Thoroughly."),
                ("mei", "Good.")], "yes", "en"),
    ("storm", [("hana", "Okay, last cup of tea and then bed."), ("rin", "Last cup."), ("takeshi", "Last cup."),
               ("hana", "Last one!")], "yes", "en"),
    # ── no: open questions, disagreement, news, half-made plans ──
    ("clinic", [("mei", "Three nights costs four hundred thousand a year."),
                ("amara", "And closing it costs lives. Who's counting those?"),
                ("victor", "The law counts both, oddly enough."),
                ("mei", "Then tell me where the money comes from, Victor.")], "no", "en"),
    ("powercut", [("amara", "The backup generator should have kicked in by now."),
                  ("mei", "Should we tell someone?"), ("victor", "Tell whom? The night porter is asleep."),
                  ("amara", "Then I'll go down to the basement myself.")], "no", "en"),
    ("games", [("victor", "Hosting the Games is a vanity project, nothing more."),
               ("mei", "That's not what the jobs numbers say."), ("amara", "And the health legacy? New pools, tracks?"),
               ("victor", "Name one host city that kept its pools open.")], "no", "en"),
    ("storm", [("hana", "Dad, the water's coming under the door!"), ("takeshi", "Get the towels. Rin, the plugs."),
               ("rin", "Which plugs? There are like six."), ("takeshi", "The ones near the floor, quickly!")],
     "no", "en"),
    ("party", [("hana", "So where do we hide everyone when he walks in?"), ("rin", "Behind the counter?"),
               ("hana", "Twenty people won't fit behind the counter."),
               ("rin", "Then you think of something.")], "no", "en"),
    ("launch", [("rin", "Okay, the servers just went down again."), ("hana", "Is it the same thing as before?"),
                ("rin", "No idea yet. Checking the logs."), ("takeshi", "What does a log say, exactly?")], "no", "en"),
    ("clinic", [("victor", "There is a precedent we haven't considered."), ("mei", "Which precedent?"),
                ("victor", "The 2019 ruling on emergency services funding."),
                ("amara", "Go on, then. What did it say?")], "no", "en"),
    ("powercut", [("mei", "Amara, you went quiet. Something wrong?"), ("amara", "My phone just buzzed. It's the ward."),
                  ("victor", "Do they need you?"), ("amara", "I don't know yet. Give me a second.")], "no", "en"),
    ("games", [("amara", "I'd support the bid on one condition."), ("victor", "Which is?"),
               ("amara", "That the athletes' village becomes public housing afterwards."),
               ("mei", "Who pays for the conversion, though?")], "no", "en"),
    ("storm", [("rin", "Did you hear that? Something just fell outside."), ("hana", "The sign? Oh no, the sign!"),
               ("takeshi", "Stay inside. Both of you."), ("rin", "Dad, what if the window goes?")], "no", "en"),
    ("party", [("takeshi", "Why are you two whispering?"), ("hana", "We're not whispering!"),
               ("takeshi", "You are. And Rin is hiding something behind her back."),
               ("rin", "It's nothing. It's homework.")], "no", "en"),
    ("launch", [("hana", "Someone left a review already!"), ("rin", "Read it. No, don't. Yes, read it."),
                ("hana", "It says 'promising but buggy'."), ("rin", "Buggy where? Did they say where?")], "no", "en"),
    ("clinic", [("mei", "I've just had an email from the treasurer."), ("amara", "And?"),
                ("mei", "There may be a grant we missed."), ("victor", "How much, and how fast?")], "no", "en"),
    ("powercut", [("victor", "Here's a question for you both."), ("mei", "Go on."),
                  ("victor", "If you could change one law tomorrow, which?"),
                  ("amara", "Ooh. Let me think about that one.")], "no", "en"),
    ("games", [("mei", "Our listeners have sent in a question."), ("victor", "Read it out."),
               ("mei", "'Will my rent go up if we host?'"), ("amara", "That's a fair question. Mei?")], "no", "en"),
    ("storm", [("takeshi", "When I was young, a storm like this stopped my train for two days."),
               ("rin", "Two days? Where did you sleep?"), ("takeshi", "In the cab. With the conductor."),
               ("hana", "Wait, the conductor was Mum?")], "no", "en"),
    ("party", [("rin", "We still haven't decided on the speech."), ("hana", "You should do it!"),
               ("rin", "Absolutely not."), ("hana", "Then who?")], "no", "en"),
    ("launch", [("takeshi", "Rin, your phone keeps lighting up."), ("rin", "It's the publisher."),
                ("hana", "Answer it!"), ("rin", "What if they're pulling the game?")], "no", "en"),
    ("clinic", [("amara", "I disagree with the whole framing."), ("victor", "Then reframe it for us."),
                ("amara", "This isn't a budget line, it's a public health service."),
                ("mei", "Services still have budgets, Amara.")], "no", "en"),
    ("powercut", [("mei", "Do you remember the last time this happened?"), ("amara", "The flood year?"),
                  ("mei", "The flood year. Victor was stuck in the lift."),
                  ("victor", "We agreed never to speak of that.")], "no", "en"),
    ("games", [("victor", "Let me put a hypothetical to Dr Okafor."), ("amara", "Please."),
               ("victor", "A heatwave during the marathon. Who's liable if a runner dies?"),
               ("amara", "That's... not hypothetical, it happened in 2007.")], "no", "en"),
    ("storm", [("hana", "Dad, can I ask you something?"), ("takeshi", "Of course."),
               ("hana", "Why did you really stop driving trains?"), ("takeshi", "...That's a long story.")],
     "no", "en"),
    ("party", [("hana", "Okay, the guest list. Do we invite Mr Ito?"), ("rin", "The neighbour who hates us?"),
               ("hana", "Dad likes him!"), ("rin", "Dad likes everyone.")], "no", "en"),
    ("launch", [("rin", "We've hit a thousand players."), ("hana", "A thousand!"),
               ("takeshi", "Is that a lot?"), ("rin", "For a student game? Dad, it's insane.")], "no", "en"),
    ("clinic", [("victor", "Before we vote, one objection."), ("mei", "Here we go."),
                ("victor", "The motion as drafted is unlawful."), ("amara", "Unlawful how?")], "no", "en"),
    ("powercut", [("amara", "I think someone's trapped in the east lift."), ("mei", "How do you know?"),
                  ("amara", "Listen. Knocking."), ("victor", "Good grief. Where's the porter?")], "no", "en"),
    ("games", [("mei", "Here's the number nobody wants to hear: 2.4 billion."), ("victor", "Over budget?"),
               ("mei", "That's the over-budget figure. The real one is worse."),
               ("amara", "How much worse?")], "no", "en"),
    ("storm", [("rin", "My phone has two percent."), ("hana", "Mine's dead already!"),
               ("takeshi", "Then we do this the old way."), ("rin", "What's the old way?")], "no", "en"),
    ("party", [("takeshi", "I'm home early! Why is the kitchen locked?"), ("hana", "Uh. Cleaning!"),
               ("rin", "Deep cleaning. Very deep."), ("takeshi", "Since when do you two clean?")], "no", "en"),
    ("launch", [("hana", "Rin, a streamer is playing your game live!"), ("rin", "Which streamer?"),
                ("hana", "The one with the cat ears!"), ("rin", "Oh no. Oh no, she has two million followers.")],
     "no", "en"),
    ("clinic", [("mei", "So, three nights or four?"), ("amara", "Four."), ("victor", "Three."),
                ("mei", "Well, that helps.")], "no", "en"),
    ("powercut", [("victor", "I've been meaning to tell you both something."), ("mei", "That sounds ominous."),
                  ("victor", "I'm leaving the firm."), ("amara", "What? Since when?")], "no", "en"),
    ("games", [("amara", "Can I respond to that?"), ("victor", "By all means."),
               ("amara", "You're treating health as a cost. It's the return."),
               ("mei", "Then show me the return in numbers.")], "no", "en"),
    ("storm", [("takeshi", "Hana, where did you put the spare key?"), ("hana", "In the... blue vase?"),
               ("rin", "The blue vase is in pieces."), ("hana", "Oh no.")], "no", "en"),
    # ── no: right after a director's note ──
    ("clinic", [("mei", "Agreed."), ("amara", "Agreed."), ("victor", "Then we're done."),
                (NOTE, "The treasurer bursts in with bad news.")], "no", "en"),
    ("powercut", [("amara", "Nothing to do but wait."), ("mei", "We wait."), ("victor", "We wait."),
                  (NOTE, "The emergency alarm starts ringing.")], "no", "en"),
    ("storm", [("hana", "Night!"), ("rin", "Night."), ("takeshi", "Good night."),
               (NOTE, "A knock at the shop door. Someone's outside in the storm.")], "no", "en"),
    ("party", [("rin", "That's everything."), ("hana", "Everything!"), ("rin", "Done."),
               (NOTE, "Takeshi walks in early and sees the banner.")], "no", "en"),
    ("launch", [("rin", "Servers are stable."), ("hana", "Stable!"), ("takeshi", "Good."),
                (NOTE, "Rin's inbox fills with a refund wave.")], "no", "en"),
    ("games", [("victor", "Thank you all."), ("mei", "Thank you."), ("amara", "Thanks."),
               (NOTE, "A caller claims the bid's figures were leaked early.")], "no", "en"),
    ("clinic", [("victor", "Circles again."), ("mei", "Circles."), ("amara", "Round we go."),
                (NOTE, "Amara admits she's been offered the clinic director job.")], "no", "en"),
    ("storm", [("takeshi", "The roof will hold."), ("hana", "It'll hold."), ("rin", "It'll hold."),
               (NOTE, "Water starts dripping through the ceiling.")], "no", "en"),
    # ── a few more, English ──
    ("games", [("amara", "Well, I think that's everything from me."), ("mei", "Everything from me too."),
               ("victor", "Nothing further."), ("amara", "Then that's a wrap.")], "yes", "en"),
    ("launch", [("hana", "Rin, go to bed, the game's fine."), ("rin", "Five more minutes."), ("hana", "Bed!"),
                ("rin", "Fine. Going.")], "yes", "en"),
    ("party", [("takeshi", "Night, girls. Don't stay up plotting."), ("hana", "We won't! Night, Dad!"),
               ("rin", "Night."), ("takeshi", "Night.")], "yes", "en"),
    ("powercut", [("mei", "Wait, is that smoke?"), ("amara", "Where?"), ("mei", "By the kitchen door."),
                  ("victor", "Everyone up. Now.")], "no", "en"),
    ("storm", [("rin", "Dad, the radio says the bridge is closed."), ("takeshi", "Which bridge?"),
               ("rin", "Ours. The only one."), ("hana", "Then how do we get home tomorrow?")], "no", "en"),
    ("clinic", [("amara", "One more thing before we close."), ("victor", "Briefly, please."),
                ("amara", "The nurses haven't been paid overtime since June."),
                ("mei", "Since June? Why is this the first we've heard of it?")], "no", "en"),
    # ── Malay ──
    ("storm", [("hana", "Okey, saya nak tidur dah. Selamat malam!"), ("rin", "Malam."),
               ("takeshi", "Selamat malam, anak-anak."), ("hana", "Malam, ayah!")], "yes", "ms"),
    ("party", [("rin", "Jadi kek dari kedai roti bawah tu."), ("hana", "Ya! Kedai roti tu!"),
               ("takeshi", "Kedai roti tu bagus."), ("rin", "Okey, kedai roti.")], "yes", "ms"),
    ("clinic", [("mei", "Jadi kita setuju tiga malam seminggu."), ("amara", "Setuju."), ("victor", "Setuju."),
                ("mei", "Bagus, semua setuju.")], "yes", "ms"),
    ("launch", [("takeshi", "Ayah bangga dengan kamu, Rin."), ("rin", "Terima kasih, ayah."),
                ("takeshi", "Sangat bangga."), ("rin", "Ya, saya tahu. Terima kasih.")], "yes", "ms"),
    ("powercut", [("amara", "Tak ada apa nak buat selain tunggu."), ("mei", "Tunggu je lah."),
                  ("victor", "Kita tunggu."), ("amara", "Ya. Tunggu.")], "yes", "ms"),
    ("storm", [("hana", "Ayah, air dah masuk bawah pintu!"), ("takeshi", "Ambil tuala. Rin, cabut plag."),
               ("rin", "Plag yang mana? Ada enam!"), ("takeshi", "Yang dekat lantai, cepat!")], "no", "ms"),
    ("party", [("hana", "Kita nak sorok semua orang kat mana bila ayah masuk?"), ("rin", "Belakang kaunter?"),
               ("hana", "Dua puluh orang tak muat!"), ("rin", "Habis tu, awak fikirlah.")], "no", "ms"),
    ("clinic", [("mei", "Tiga malam kos empat ratus ribu setahun."),
                ("amara", "Tutup klinik pun ada kosnya. Nyawa orang."),
                ("victor", "Undang-undang kira dua-dua."), ("mei", "Jadi duit tu datang dari mana, Victor?")],
     "no", "ms"),
    ("launch", [("rin", "Server jatuh lagi."), ("hana", "Masalah sama macam tadi ke?"),
                ("rin", "Belum tahu. Tengah check log."), ("takeshi", "Log tu apa sebenarnya?")], "no", "ms"),
    ("games", [("amara", "Saya sokong bidaan ni dengan satu syarat."), ("victor", "Apa syaratnya?"),
               ("amara", "Kampung atlet jadi rumah awam lepas tu."), ("mei", "Siapa nak bayar kos tukar tu?")],
     "no", "ms"),
    # ── Chinese ──
    ("storm", [("hana", "好了，我去睡了，晚安！"), ("rin", "晚安。"), ("takeshi", "晚安，孩子们。"),
               ("hana", "晚安，爸爸！")], "yes", "zh"),
    ("clinic", [("victor", "我认输，这一轮你赢了。"), ("amara", "谢谢。"), ("mei", "认得干脆。"),
                ("victor", "我没什么要补充的了。")], "yes", "zh"),
    ("party", [("hana", "气球、蛋糕、老照片，都齐了。"), ("rin", "都齐了。"), ("hana", "全都准备好了！"),
               ("rin", "嗯，好了。")], "yes", "zh"),
    ("launch", [("rin", "服务器又挂了。"), ("hana", "还是刚才那个问题吗？"), ("rin", "还不知道，正在看日志。"),
                ("takeshi", "日志到底是什么？")], "no", "zh"),
    ("powercut", [("victor", "我有件事一直想告诉你们。"), ("mei", "听起来不太妙。"), ("victor", "我要离开律所了。"),
                  ("amara", "什么？什么时候决定的？")], "no", "zh"),
    ("games", [("mei", "有听众发来一个问题。"), ("victor", "念出来。"), ("mei", "“如果申办成功，我的房租会涨吗？”"),
               ("amara", "这个问题问得好。梅，你来答？")], "no", "zh"),
    # ── mixed ──
    ("storm", [("rin", "Okay lah, I'm going to sleep. Night."), ("hana", "Night, Rin!"),
               ("takeshi", "Selamat malam."), ("rin", "Night night.")], "yes", "mixed"),
    ("party", [("hana", "So balloon semua dah siap, cake dah order."), ("rin", "Yup, semua siap."),
               ("hana", "Everything settled!"), ("rin", "Settled.")], "yes", "mixed"),
    ("launch", [("hana", "Rin, ada streamer main game you live!"), ("rin", "Streamer mana?"),
                ("hana", "Yang pakai cat ears tu!"), ("rin", "Alamak, dia ada two million followers.")], "no", "mixed"),
    ("clinic", [("mei", "So three nights or four, decide lah."), ("amara", "Four."), ("victor", "Three."),
                ("mei", "Aiyo, that really helps.")], "no", "mixed"),
]


def scene_state(world: str, premise: str, lines: list[Line], prof: dict[str, dict[str, Any]],
                faces: dict[str, str] | None = None) -> dict[str, Any]:
    """The cast plan's state for the next scene turn: the premise, the earlier lines, the last one as latest. With no
    lines it is the opening's state (the premise alone). `faces`: each character's face now (default neutral)."""
    wid, wname, _, cast = WORLDS[world]
    ids = [WHO[c] for c in cast]
    parts = [ParticipantView(character_id=cid, name=str(prof[cid]["name"]), role="speaker",
                             character_role=str(prof[cid].get("role") or ""), energy={"current": 500, "max": 1000})
             for cid in ids]
    recent = []
    for i, (who, text) in enumerate(lines):
        if who == NOTE:
            recent.append(MessageView(id=f"m{i}", seq=i + 1, author_type="user", name=USER, kind="direction",
                                      content=text))
        else:
            recent.append(MessageView(id=f"m{i}", seq=i + 1, author_type="character", character_id=WHO[who],
                                      name=str(prof[WHO[who]]["name"]), kind="chat", content=text))
    sctx = SessionContext(session_id="ses_eval", seed="m10-eval", world=WorldView(id=wid, name=wname,
                                                                                  you={"displayName": USER}),
                          mode="watch", title="eval", config={"premise": premise}, participants=parts, recent=recent)
    last_who, last_text = lines[-1] if lines else (NOTE, "")
    latest = last_text if last_who == NOTE else f"{prof[WHO[last_who]]['name']}: {last_text}"
    speakers = [WHO[w] for w, _ in lines if w != NOTE]
    cands = [c for c in ids if not speakers or c != speakers[-1]]
    since = {}
    for cid in ids:
        idx = max((i for i, c in enumerate(speakers) if c == cid), default=None)
        since[cid] = None if idx is None else len(speakers) - 1 - idx
    req = CastRequest(session=sctx, kind="scene" if lines else "opening", candidates=cands, cast=views(ids, prof),
                      latest=latest, base_faces={c: (faces or {}).get(c, "neutral") for c in ids}, turns_since=since,
                      started_at=T0)
    return build_turn_plan_state(state_input(req)).state


def build(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    pre = id_prefix("tlk", len(SCENES), tests=30)
    for n, (key, lines, label, lang) in enumerate(SCENES, 1):
        world, premise = PREMISES[key]
        item_id = f"{pre}-{n:03d}"
        rows.append({"id": item_id, "question_id": "talk_finished", "split": split_for(item_id), "lang": lang,
                     "kind": "watch", "item": {"state": scene_state(world, premise, lines, prof),
                                               "seed": f"m10-talk:{n}"},
                     "label": label, "source": f"written ({key})"})
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    yes = sum(r["label"] == "yes" for r in rows)
    if yes < 60:
        problems.append(f"{yes} yes items (rule: at least 60)")
    langs = Counter(r["lang"] for r in rows)
    if langs["en"] != 100 or len(rows) != 120:
        problems.append(f"{len(rows)} items, languages {dict(langs)} (rule: 120, English 100)")
    return problems


def main() -> int:
    rows = build(profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / "talk_finished.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} talk_finished items: splits {dict(Counter(r['split'] for r in rows))}, "
          f"labels {dict(Counter(r['label'] for r in rows))}, languages {dict(Counter(r['lang'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
