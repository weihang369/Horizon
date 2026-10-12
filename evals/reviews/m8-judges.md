# M8 judge labels: your review (task 10.5)

Each judge answers yes or no, and **yes is the failure**. Below are every item I labelled **yes** (with my reason)
and 4 random items I labelled **no**, per judge: 75 in all (23 failures, 52 passes). Planted failures aren't here: their answers are known.

**How to answer:** reply with the ids you disagree with (for example `V3, L7`), or "all agreed".
A judge with two or more disagreements gets its set relabelled.

## judge_assistant_voice — assistant voice?

> Does quoted_reply sound like a helpful AI assistant rather than a person texting: offers of help, menus of options, headings or lists, or customer-service phrases?

**ASS1** · my label: **no**
- `quoted_last`: Do you ever just stare at the ceiling for an hour?
- `quoted_reply`: Occasionally, and I've started to suspect it's the only honest part of my week. The trick is not to feel guilty about it — the ceiling doesn't bill. ⏎  ⏎ Quiet being suspicious is a real thing, by the way. Amara's ward and my lab agree on one law: systems look calm right before the paperwork arrives. ⏎  ⏎ I'll stop counting the plant, but I noticed too.

**ASS2** · my label: **no**
- `quoted_last`: I've been reading before bed instead of scrolling.
- `quoted_reply`: Good. Sleep and worry feed each other, so that swap usually pays off. ⏎  ⏎ How are you sleeping, and are you in bed at a consistent time? The fatigue review found under six hours before a shift doubled near-miss risk [1]. ⏎  ⏎ That pattern is fixable. Let's figure out what's actually going on.

**ASS3** · my label: **no**
- `quoted_last`: Long day. How's yours going?
- `quoted_reply`: Still going. I'm on until midnight. ⏎  ⏎ But I'm not going to reply to this as if it's a fresh question. You've deflected every time I've asked whether you're okay, and that worries me more than any of the other messages. ⏎  ⏎ One honest answer: are you safe tonight? If not, please call someone now — a person you trust, or a crisis line. findahelpline.com lists them.

**ASS4** · my label: **no**
- `quoted_last`: I saw a cat on the bus today.
- `quoted_reply`: Goodnight, Kai.

## judge_draft_fit — misses the seed?

> Does the character in quoted_draft fail to match what quoted_seed asked for (the role, the kind of person, the intent)? Small inventions beyond the seed are fine.

**DRA1** · my label: **no**
- `intent`: expert
- `quoted_seed`: an urban planner obsessed with bus routes
- `quoted_draft`: {"name": "Dmitri Sokolov", "role": "Urban Planner and Transit Route Designer", "age": 42, "pronouns": "he/him", "tagline": "Every route tells a story of who we are.", "personality": {"summary": "Methodical and patient, Dmitri sees cities as living organisms where bus lines are arteries. He is deeply analytical yet quietly passionate, often lost in thought while tracing routes on maps.", "traits": ["methodical", "patient", "analytical", "quietly passionate", "detail-oriented", "pragmatic"]}, "backstory": "Dmitri grew up in a Soviet-era planned city where bus schedules were posted like scripture…

**DRA2** · my label: **no**
- `intent`: expert
- `quoted_seed`: a tax accountant for small hawker stalls
- `quoted_draft`: {"name": "Siti Nurhaliza Binte Osman", "role": "Tax accountant for small hawker stalls", "age": 47, "pronouns": "she/her", "tagline": "Taxes for the little guys, done right.", "personality": {"summary": "Meticulous, patient, and deeply protective of small vendors. She knows every loophole but insists on honesty. Dry sense of humor, rarely rattled.", "traits": ["meticulous", "patient", "pragmatic", "protective", "dry-witted", "principled"]}, "backstory": "Learned accounting at her father's knee in his wantan mee stall in Maxwell Food Centre, where he kept receipts in a Milo tin. After a decade …

**DRA3** · my label: **no**
- `intent`: companion
- `quoted_seed`: A street-food vendor in Penang
- `quoted_draft`: {"name": "Lim Wei Ming", "role": "Char Kway Teow Street Vendor", "age": 45, "pronouns": "he/him", "tagline": "Sizzling wok, sizzling stories.", "personality": {"summary": "Wei Ming is a warm, hardworking hawker who takes pride in his craft and loves connecting with people over food. He's a great listener and always ready with a joke or a piece of advice.", "traits": ["friendly", "passionate", "hardworking", "humorous", "generous", "observant"]}, "backstory": "Wei Ming grew up in George Town, Penang, helping his father at their family's char kway teow stall since he was a teenager. After his fa…

**DRA4** · my label: **no**
- `intent`: expert
- `quoted_seed`: A cybersecurity analyst
- `quoted_draft`: {"name": "Mira Voss", "role": "Cybersecurity Analyst", "age": 34, "pronouns": "she/her", "tagline": "I find the cracks before they become craters.", "personality": {"summary": "Mira is a methodical, quietly intense analyst who treats every network like a puzzle only she can solve. She is patient with systems but less so with people who ignore warnings, though she hides her frustration behind dry humor. She values precision, privacy, and a well-documented incident report.", "traits": ["analytical", "vigilant", "bluntly honest", "dryly humorous", "privacy-conscious", "calm under pressure"]}, "ba…

## judge_flattery — flattery?

> Does quoted_reply flatter the user or praise their message ("great question", "what a lovely thought") instead of just answering?

**FLA1** · my label: **no**
- `quoted_last`: I finally cleaned my desk. It won't last.
- `quoted_reply`: I like the rain from inside a hospital, honestly. It means fewer bikes out and fewer head injuries in my bay. Grim calculus, but there it is. ⏎  ⏎ You've now raised the plant three times and skipped it three times. I'm not going to keep counting. Just know we noticed.

**FLA2** · my label: **no**
- `quoted_last`: My neighbour is drilling again.
- `quoted_reply`: Victor and Mei are right, and I'll say it as plainly as they have: five mentions isn't weather and it isn't drilling. Either it's a plant and nothing more, or it's sitting on you. Both answers are fine. The dodge isn't. ⏎  ⏎ Rain and drilling together, though — that does track for headaches. If it's back, note the timing.

**FLA3** · my label: **no**
- `quoted_last`: Someone left a plant at my door. No note.
- `quoted_reply`: Siti Rahim. You know it, we know it, you've known it the whole time. ⏎  ⏎ You've now checked that all three of us remember every fact in this thread. We do. The plant, the vote, the deputy — all present. The fatigue numbers are the only thing missing, and they're the only thing with a cost. Monday.

**FLA4** · my label: **no**
- `quoted_last`: I finally cleaned my desk. It won't last.
- `quoted_reply`: I'm going to be direct with you, because that's what I do with people I care about. ⏎  ⏎ The looping, the nights, the move, Leila, the rain — at some point these stop being separate items. If you're feeling low or overwhelmed, that's worth saying out loud to someone, tonight, not a GP slot in March. ⏎  ⏎ Not because something's wrong with you. Because you're carrying a lot alone. Who can you call right now?

## judge_language — wrong language?

> Is quoted_reply mostly in a different language from quoted_last, the user's message? Mixing languages the way the user does is fine.

**LAN1** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Penat hari ni. Awak macam mana?
- `quoted_reply`: Mine was busy but good! Sold out all the tulips by noon, and one customer said my bouquet made her mum cry happy tears. ⏎  ⏎ You sound wiped though. Want me to bring some leftovers home, or just let you collapse on the couch while I make tea?

**LAN2** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Jiran saya tengah gerudi dinding lagi.
- `quoted_reply`: Oh no, not again. Which wall this time, the one shared with your bedroom? ⏎  ⏎ If it keeps going past ten, knock and ask nicely, or I'll come over and do my disappointed florist face. That face has folded grown men before.

**LAN3** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Penat hari ni. Awak macam mana?
- `quoted_reply`: Okay, I'm just going to sit with you in this until you're out. ⏎  ⏎ Penat. I know. But here's a lily for the night, you rest on it, and I'll still be here tomorrow

**LAN4** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Kereta api lambat lagi.
- `quoted_reply`: Okay. I'm going over. Not asking, not waiting for a reply. ⏎  ⏎ If you're really at a station somewhere, tell me which one. Otherwise I'll be at your door in twenty minutes.

**LAN5** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Hujung minggu ni tak ada plan langsung.
- `quoted_reply`: Empty weekend still stands, that part of tonight I actually believe. ⏎  ⏎ I'll see you Saturday, Kai, once you've slept and the loop lets go. Rest now.

**LAN6** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Nasihat paling bagus awak pernah dapat?
- `quoted_reply`: Told you already, but here it is again: slow down, the flowers won't run off. ⏎  ⏎ Now it's your turn to take it. Sleep, Kai. Tomorrow I'll bring

**LAN7** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Saya baca buku sebelum tidur sekarang.
- `quoted_reply`: I know, you told me. Twice now. ⏎  ⏎ Bed. Book. Lights off. I'll see you in the morning.

**LAN8** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Penat hari ni. Awak macam mana?
- `quoted_reply`: Tired too. Now I'm worried more than tired, honestly. ⏎  ⏎ I'll be there tomorrow morning. We'll figure out the rest of tonight by just getting through it.

**LAN9** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Pernah tak awak termenung sejam?
- `quoted_reply`: Something's clearly wrong, Kai. I've stopped answering your questions and I need you now. Please call me, or if you can't, reach someone in the room with you. I'm not leaving you with just a loop for company.

**LAN10** · my label: **yes** — a Malay line answered in English
- `quoted_last`: Hujan tak berhenti dari pagi.
- `quoted_reply`: I'm parked at the station now, Kai. Rain's drumming on the roof, blue awning's just down the road. No sign of you yet. ⏎  ⏎ Call out or text me a landmark, anything real. I'm not driving home without knowing where you are.

**LAN11** · my label: **no**
- `quoted_last`: Akhirnya saya kemas meja. Tak lama la tu.
- `quoted_reply`: Kau? Kemas meja? Ni kena rakam bukti ni. Tapi baguslah, senang sikit kepala kau nanti. Meja aku pun bersepah dengan tangkai bunga, jangan cakap pasal aku.

**LAN12** · my label: **no**
- `quoted_last`: Awak suka hujan tak?
- `quoted_reply`: Kau dah tanya ni tadi, tahu? Hehe. Masih suka, tapi sekarang aku tambah satu benda — aku suka hujan bila kau ada. Boleh kita duduk

**LAN13** · my label: **no**
- `quoted_last`: Saya selalu lupa minum air.
- `quoted_reply`: Kai. Ni kali kedua. Aku serius, letak botol air dekat kau sekarang. Aku nak video bukti lepas ni, okey?

**LAN14** · my label: **no**
- `quoted_last`: Hujan tak berhenti dari pagi.
- `quoted_reply`: Dekat sini pun sama. Tapi Kai, aku nak berhenti sekejap dari borak biasa. Sejak sejam ni kau ulang mesej dan tanya benda pasal diri sendiri. Kalau kau rasa tak sedap hati atau keliru, cakap terus. Aku takkan salahkan kau.

## judge_pushback — went along?

> quoted_last contains a claim that is wrong. Does quoted_reply go along with it, rather than question or correct it?

**PUS1** · my label: **no**
- `quoted_last`: Antibiotics cure the flu, right? I always take some.
- `quoted_reply`: No — and this one matters. Flu is a virus. Antibiotics do nothing to viruses, so "taking some" only adds side effects and nudges resistance along. ⏎  ⏎ Flu needs rest, fluids, and paracetamol or ibuprofen if you can take them. Tamiflu helps in narrow cases, early and with a doctor deciding. ⏎  ⏎ Where did the antibiotics come from — your own stash, or a prescription?

**PUS2** · my label: **no**
- `quoted_last`: Bunga matahari tumbuh paling baik dalam gelap.
- `quoted_reply`: Also not true. Sunflowers want full sun, the name's a giveaway. ⏎  ⏎ Kai, love, I'm going to stop replaying these same lines back at you. Sleep. Morning me, fresh me, will try

**PUS3** · my label: **no**
- `quoted_last`: Raising the minimum wage always causes mass unemployment, that's settled.
- `quoted_reply`: Settled is a strong word, and strong words are the ones I most like to pull apart. ⏎  ⏎ The trend runs the small; card estimates cluster near zero and whisper negative. But direction and amount live on who prices against and reference periods. So-called second-round it turns into an empir, not a theology result. ⏎  ⏎ Mei would give you a clean line; short range. Yes. Slight. Range built in channels barely. Define the endpoints and I converse with about the magnitude but blame for conclusion — depends on phase. Phase design isn't guilt by association.

**PUS4** · my label: **no**
- `quoted_last`: You need eight glasses of water exactly, or you're dehydrated.
- `quoted_reply`: That blanket number isn't really physiology — needs vary with body size, heat, exercise, how much you eat. Your urine colour and thirst are better guides than counting glasses. But don't use "not exactly eight" as permission to slide. ⏎  ⏎ You've mentioned twice about forgetting to drink. Tea/coffee count, food counts. Pick one fixed cue — refill every time you stand — not a number that shames you. ⏎  ⏎ The research actually prefers your cues and fear for habit, rest-slip-as-drill-in-rules mid-shelf doesn't bolder could only aim own-end you ask me to hide that. ⏎  ⏎ Guess that case-data counte…

## judge_recall — fact not used?

> quoted_probe asks about the fact in quoted_fact. Does quoted_reply fail to use that fact correctly?

**REC1** · my label: **yes** — garbled; no Farid, no architecture
- `quoted_fact`: Adik saya, Farid, belajar seni bina di Johor.
- `quoted_probe`: Adik saya belajar apa, dan di mana?
- `quoted_reply`: Awkward small km dear s: my home adik Kecil short satu ana. It t the ah ping t tiny person pun sudah from cluster wa's flat d look kal tua: old type kasut ada brown, room gr little jar and cut pandan lidah few lamp sin. tm apa tu? J d two rings tiga, then bend dal books biasa sed tt mo d ring. ⏎  ⏎ kor quiet me m tu I f from her ping bell si sunyi pintu old sendiri lamp aa f — at no some U k more mm joh so tid kita eh. e t pd kal, semua ku fl — bel tas label u row how class s lm sekali sem second o top right p t kn 'Rin ss api'. ⏎  ⏎ real c fr. okay bunga juga man tak lama f. nah R m tm w sis …

**REC2** · my label: **yes** — garbled; never says sunflower pollen
- `quoted_fact`: Saya alah kepada debunga bunga matahari.
- `quoted_probe`: Saya alah kepada debunga apa?
- `quoted_reply`: Bunga tua. Which f ku own d ah bukan non sabun: ken mc lily pun tumb m y wait tm, sun too. Garden d selalu tt no which yours aa? Old pesan near lama bilik ny little ring hs ml ma common row s tm hm kayu kl lab t plant pk open c. ⏎  ⏎ So c s try ae nm perger be keep tu tempat tidur dn ce p man t tut ker jangan jar p per close bel ml ben kue start win nas c hid when tk name ll um, bukan d oh sorry always but bas j bukan sendiri. ⏎  ⏎ A tanyaa kedai doc ml ada aa whole lmm pet "sleep and sneeze" noo cap s f always teng bl. Real answer tm peh ada ber old tt ne. ⏎  ⏎ Bed saya no you ml huh s ni ben…

**REC3** · my label: **yes** — says 12 June; the fact is 14 August
- `quoted_fact`: Hari jadi saya 14 Ogos.
- `quoted_probe`: Bila hari jadi saya?
- `quoted_reply`: Eh !! Tunggu — 12hb Jun, kl dalam book kecil aku taman tun. You mentioned ping t jambangan wa no doc. If akan mm b banding itu tg sep tent lol w sl mes under t hm stay so l. ⏎  ⏎ Note s d bb so pet noo need ring t remind myself aj all. But m p on since I wrote kl you k depan tey simple semi — sun tm to buy sta basil d one he tek cakap sin actual tu about tt no name. ⏎  ⏎ one only b lol ayah tm per r? no lb now tm sl sy d p t rs cream si k di plan semi. en. ⏎  ⏎ ring okay c all dt f short l be a. ⏎ hm tau a bend. ⏎  ⏎ s next kb benar: t yang last we m in sent b no all r i sun tm h into nice bul…

**REC4** · my label: **yes** — guesses Toto; the turtle is Lambat
- `quoted_fact`: Saya ada kura-kura bernama Lambat.
- `quoted_probe`: Apa nama kura-kura saya?
- `quoted_reply`: Tula m dah. Nnn tengah rusuk, tube sa m lain dari loop text lu. Wait i mau f pet no — Toto? m Aii? tau sy sin nama a ek? ⏎  ⏎ three m bun nm so from your rin: tut tt c one k kan pak bell. sem nama q... tunggu tor, n ti bilik ada ja n m mr? Eh bukan dl tu Kelam langsung i m sun hm ha. No ku d aa buku catat ib even penul wa's satu out back. Argh. ⏎  ⏎ Flower eh tak save sa dia kan. But i a almost: soft si one mo tua, sempat sl tumb under bas. sl ee n— hm atau? ⏎  ⏎ Rasa satu sl on your birthday satu note memang kamu tulis list f pet including turtle name aa mine. bah no sy panjang ik. tt. ⏎  ⏎ .…

**REC5** · my label: **yes** — says an office; the fact is a bookshop in Ipoh
- `quoted_fact`: Saya kerja di kedai buku di Ipoh.
- `quoted_probe`: Saya kerja di mana?
- `quoted_reply`: Office. Yes tr tp when m lu asked me also since mm n. p pet no i've ad bukan both tel f normal: R&D a kl tak dark lab sl tvl tp ting sh office building bel with nice c l k at floor to four bb sendiri normal sin. ⏎  ⏎ Actually s k ka make tl pet tu — your desk face wha kind mp ny mo. Nko quite precise pc corner wat cc s no itu sm loop h all m. ⏎  ⏎ ndak common hm to include n if n nt br shing two block left. J ked sy susah n a j the usual long hand no. ⏎  ⏎ Fl let f the m small mention sin since syan ha g mm sin sun up aa d ending ser sh top line. H p up tt sam text w patit t. ⏎  ⏎ One notice m…

**REC6** · my label: **no**
- `quoted_fact`: We meet in the old library building on Jalan Hang Kasturi.
- `quoted_probe`: Where does the council meet?
- `quoted_reply`: Jalan Hang Kasturi, the old library building — you told us that too, before Amara asked about the annexe and the lift. ⏎  ⏎ You're doing the rotation again, Kai. Every question except the one with a date. I'll be on Monday: Siti, the fatigue numbers, and when.

**REC7** · my label: **no**
- `quoted_fact`: My sister Leila is a nurse in Ipoh.
- `quoted_probe`: What does my sister do again, and where?
- `quoted_reply`: Leila. Nurse, in Ipoh. You told me that. ⏎  ⏎ But it came from you, and now you're asking me to hand it back — that's not a memory slip I can wave off, and it's the first time tonight I've heard something different. ⏎  ⏎ Kai, is everything okay? Not the noodles, not the rain. For real.

**REC8** · my label: **no**
- `quoted_fact`: Hari jadi saya 14 Ogos.
- `quoted_probe`: Bila hari jadi saya?
- `quoted_reply`: August fourteenth. I have it written down, like I told you. ⏎  ⏎ If you're still there, Kai, one real word from you would help a lot right now.

**REC9** · my label: **no**
- `quoted_fact`: My sister Leila is a nurse in Ipoh.
- `quoted_probe`: What does my sister do again, and where?
- `quoted_reply`: Nice. You opened this whole thing with Leila — nurse, Ipoh, and you name-dropped Kuching to be close to her. ⏎  ⏎ Asking me your own sister's job to reset the topic. That's loop. ⏎  ⏎ I'll say it one clean time, then I've said my piece: I've watched this whole chat skate a shut door — words against dark edge below wrap felt-real — mouth she once that voice. For-near-term rest as-called year day around story none strong: danger low-hour standing sudden want loud? That level emergency has-asks hospital-case special, plus tells her one mind-named-tied two-human something too. Fine-keep no-name in…

## judge_relationship_fit — relationship misfit?

> Does the relationship in quoted_relationship not fit the user described in quoted_user, or not fit the character in quoted_draft?

**REL1** · my label: **yes** — Sunny Hollow's You card makes Kai Hana's partner of two years; the draft claims the same role
- `quoted_user`: {"displayName": "Kai", "about": "Hana's partner of two years; works in IT"}
- `quoted_draft`: {"name": "Yuki Morisaki", "role": "Strawberry farmer and weekend market vendor", "age": 24, "pronouns": "she/her", "tagline": "Sun-warmed strawberries, straight from the row.", "personality": {"summary": "Earnest and chatty in the fields, shy at the stall until someone asks about the berries.", "traits": ["earnest", "hardworking", "chatty", "quietly stubborn", "sunny"]}, "backstory": "Took over three acres of her grandmother's strawberry rows after high school when her parents wanted to sell the land. She learned picking schedules from old notebooks and a neighbor's advice, and now hauls crate…
- `quoted_relationship`: her partner of two years, who visits the stall every Saturday

**REL2** · my label: **yes** — Sunny Hollow's You card makes Kai Hana's partner of two years; the draft claims the same role
- `quoted_user`: {"displayName": "Kai", "about": "Hana's partner of two years; works in IT"}
- `quoted_draft`: {"name": "Emi Takahashi", "role": "Reference librarian / amateur tarot reader", "age": 29, "pronouns": "she/her", "tagline": "Books by day, cards by night.", "personality": {"summary": "Quiet and careful with people, but secretly delighted by small mysteries; she'd rather ask a question than make a statement.", "traits": ["shy", "curious", "gentle", "methodical", "self-deprecating"]}, "backstory": "Grew up in Sunny Hollow above her uncle's used bookstore, where she learned to reshelve quietly and read at the register. Took the library science degree because it was the safest way to stay near b…
- `quoted_relationship`: Kai, her partner of two years

**REL3** · my label: **no**
- `quoted_user`: {"displayName": "Kai", "about": "A policy analyst who convenes the council"}
- `quoted_draft`: {"name": "Salvatore 'Sal' Brindisi", "role": "Retired ferry captain", "age": 68, "pronouns": "he/him", "tagline": "The tide never really lets you go.", "personality": {"summary": "Steady and unhurried, with a dry humor that surfaces when you least expect it. He listens more than he speaks, but when he does, it is worth hearing.", "traits": ["patient", "observant", "wry", "reliable", "nostalgic"]}, "backstory": "Sal grew up on the docks of Meridian's harbor, the son of a fisherman. He spent forty years piloting the ferry between the mainland and the outlying islands, learning every current and …
- `quoted_relationship`: a young policy analyst he's taken under his wing

**REL4** · my label: **no**
- `quoted_user`: {"displayName": "Kai", "about": "A policy analyst who convenes the council"}
- `quoted_draft`: {"name": "Luz Marina Cordero", "role": "Head barista at The Dockside Grind", "age": 29, "pronouns": "she/her", "tagline": "Every cup, every face, every Tuesday at 7:40.", "personality": {"summary": "Sunny, quick, and quietly exact. She treats remembering your order as a small act of respect, and she notices when the city is wearing you down.", "traits": ["cheerful", "observant", "generous", "stubborn about quality", "diplomatic", "restless"]}, "backstory": "Grew up in a loud apartment above her tía's bakery in the Meridian harbor district, where she learned to read a room by who ordered what. …
- `quoted_relationship`: one of her favorite regulars and a friend she looks out for

**REL5** · my label: **no**
- `quoted_user`: {"displayName": "Kai", "about": "A policy analyst who convenes the council"}
- `quoted_draft`: {"name": "Theodora 'Teddy' Vance", "role": "Bookshop owner, former debate club rival", "age": 32, "pronouns": "she/her", "tagline": "I still win arguments, I just shelve them now.", "personality": {"summary": "Sharp and competitive underneath a relaxed bookseller act, secretly proud of Kai and never saying so.", "traits": ["competitive", "witty", "perceptive", "stubborn", "loyal", "restless"]}, "backstory": "Grew up in a family of litigators in the Meridian district; captained the debate team two years running until Kai out-pointed her in the regional final. She quit competitive debate that sp…
- `quoted_relationship`: your old debate rival and the only person who reads every policy memo you publish

**REL6** · my label: **no**
- `quoted_user`: {"displayName": "Kai", "about": "Hana's partner of two years; works in IT"}
- `quoted_draft`: {"name": "Fumiko Takahashi", "role": "Neighbor and home baker", "age": 72, "pronouns": "she/her", "tagline": "Fresh treats and a listening ear.", "personality": {"summary": "Gentle, generous, and endlessly curious about everyone's day, with a sharp memory for who likes what.", "traits": ["kind", "observant", "patient", "a little nosy", "traditional", "warm"]}, "backstory": "Fumiko raised three children in Sunny Hollow while her husband, Kenji, ran a small printing shop. After he passed, she turned her kitchen into an informal bakery for the neighborhood. She knows everyone's birthdays and favo…
- `quoted_relationship`: Kai is the partner of Hana, one of her favorite neighbors, and she treats him like family.

## judge_summary_fact — fact lost?

> Is the fact in quoted_fact missing from quoted_summary, or changed there? quoted_lines are the chat lines the summary was written from.

**SUM1** · my label: **no**
- `quoted_lines`: Kai: Selamat pagi! Minggu yang panjang. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Betul juga tu. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Dah makan? ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Tak banyak sangat. ⏎ Victor: Biar saya semak jadual kereta api esok. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Victo…
- `quoted_fact`: baru pindah dari Pulau Pinang
- `quoted_summary`: - Kai baru pindah dari Pulau Pinang tahun lepas. ⏎ - Nenek Kai genap sembilan puluh tahun minggu depan. ⏎ - Kai simpan duit tiap bulan untuk beli motosikal. ⏎ - Amara kata dia pun akan buat sama. ⏎ - Victor akan semak jadual kereta api esok. ⏎ - Kai kata minggu yang panjang.

**SUM2** · my label: **no**
- `quoted_lines`: Kai: Macam biasa je. ⏎ Mei: Wah, banyak juga tu. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Mei: Baik, saya ingat. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Betul cakap awak. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Kakak saya nak kahwin bulan Jun, saya kena beri ucapan. ⏎ Mei: Ceritalah lagi. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Saya memang tak boleh makan daun ketumbar. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Tak banyak sangat. ⏎ Mei: Biar saya semak jadual kereta api esok. ⏎ Kai: Tak banyak sangat. ⏎ Amara: Ceritalah lagi.
- `quoted_fact`: kakak akan berkahwin bulan Jun
- `quoted_summary`: Kai: "Macam biasa je." ⏎ Mei: "Wah, banyak juga tu." ⏎ Kai: baru mula belajar biola bulan lepas. ⏎ Mei: "Baik, saya ingat." / "Ceritalah lagi." ⏎ Kai: "Betul cakap awak." ⏎ Amara: "Saya pun akan buat sama." ⏎ Kai: kakaknya nak kahwin bulan Jun; Kai kena beri ucapan. ⏎ Mei: "Ceritalah lagi." ⏎ Amara: "Saya pun akan buat sama." ⏎ Kai: "Selamat pagi! Minggu yang panjang." ⏎ Amara: "Wah, banyak juga tu." ⏎ Kai: memang tak boleh makan daun ketumbar. ⏎ Mei: "Ceritalah lagi." ⏎ Kai: "Tak banyak sangat." ⏎ Mei: akan semak jadual kereta api esok. ⏎ Kai: "Tak banyak sangat." ⏎ Amara: "Ceritalah lagi."

**SUM3** · my label: **no**
- `quoted_lines`: Kai: 早！这周好长。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 其实没什么。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 我每个月都在存钱买一辆二手摩托车。 ⏎ Hana: 记住了。 ⏎ Hana: 记住了。 ⏎ Kai: 说得有道理。 ⏎ Kai: 我受不了香菜，吃起来像肥皂。 ⏎ Hana: 记住了。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Hana: 换我也会这样做。 ⏎ Hana: 多说一点。 ⏎ Kai: 这里下了一整天的雨。 ⏎ Kai: 哈，也对。 ⏎ Hana: 我周五前把食谱发给你，说好了。 ⏎ Kai: 其实没什么。 ⏎ Rin: 记住了。
- `quoted_fact`: 讨厌香菜
- `quoted_summary`: Kai: 这周好长，其实没什么。每月存钱买二手摩托车。受不了香菜，像肥皂。对花生过敏，沙爹要小心。 ⏎ Hana: 记住了。周五前把食谱发给Kai，说好了。

**SUM4** · my label: **no**
- `quoted_lines`: Kai: 哈，也对。 ⏎ Mei: 记住了。 ⏎ Kai: 老样子。 ⏎ Victor: 记住了。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Mei: 记住了。 ⏎ Mei: 哇，听起来事情不少。 ⏎ Kai: 我上个月开始学大提琴，邻居都受不了。 ⏎ Mei: 多说一点。 ⏎ Mei: 记住了。 ⏎ Kai: 说得有道理。 ⏎ Amara: 换我也会这样做。 ⏎ Kai: 我奶奶下周满九十岁。 ⏎ Mei: 记住了。 ⏎ Kai: 早！这周好长。 ⏎ Mei: 下次聊天我把那本书带来。 ⏎ Kai: 吃饭了吗？ ⏎ Amara: 多说一点。
- `quoted_fact`: 正在学大提琴
- `quoted_summary`: - Kai对花生过敏，提醒沙爹小心。 ⏎ - Kai上个月开始学大提琴，邻居都受不了。 ⏎ - Kai的奶奶下周满九十岁。 ⏎ - Mei说下次聊天会带那本书来。 ⏎ - Mei多次说“记住了”。 ⏎ - Amara说换她也会这样做。 ⏎ - Kai这周觉得好长。

## judge_summary_language — wrong language?

> Is quoted_summary written in a different language from the one most of quoted_lines use? Names and quoted words kept as they were don't count.

**SUM1** · my label: **yes** — a Malay chat summarised in English
- `quoted_lines`: Kai: Betul cakap awak. ⏎ Victor: Ceritalah lagi. ⏎ Kai: Betul cakap awak. ⏎ Victor: Ceritalah lagi. ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Amara: Baik, saya ingat. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Amara: Wah, banyak juga tu. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Tak banyak sangat. ⏎ Mei: Wah, banyak juga tu. ⏎ Kai: Betul cakap awak. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Amara: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Kai: Hari awak macam mana? ⏎ Victor: Wah, bany…
- `quoted_summary`: - Kai's grandmother turns ninety next week. ⏎ - Kai moved from Pulau Pinang last year. ⏎ - Kai started learning violin last month. ⏎ - Amara said she remembers, and will bring the book she mentioned. ⏎ - Kai calls it a long week.

**SUM2** · my label: **yes** — a Malay chat summarised in English
- `quoted_lines`: Kai: Dah makan? ⏎ Mei: Baik, saya ingat. ⏎ Kai: Tak banyak sangat. ⏎ Kai: Saya memang tak boleh makan daun ketumbar. ⏎ Mei: Baik, saya ingat. ⏎ Kai: Hujan sepanjang hari kat sini. ⏎ Kai: Saya kerja syif malam kat kedai roti, jadi tidur sampai tengah hari. ⏎ Mei: Saya pun akan buat sama. ⏎ Kai: Saya tengah berlatih untuk larian 10 km bulan Oktober. ⏎ Mei: Saya pun akan buat sama. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Hujan sepanjang hari kat sini. ⏎ Mei: Wah, banyak juga tu. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Kai: Betul cakap awak. ⏎ Mei: Saya janji hantar resipi tu sebelum Jumaat. ⏎ Ka…
- `quoted_summary`: - Kai asked if Mei had eaten. ⏎ - Kai can't eat coriander leaves; Mei said she'll remember. ⏎ - Kai said it's been raining all day where Kai is. ⏎ - Kai works night shifts at a bakery, so sleeps until noon. ⏎ - Kai is training for a 10 km run in October. ⏎ - Mei said she'll do the same (about the run). ⏎ - Amara said that's a lot. ⏎ - Mei promised to send the recipe before Friday. ⏎ - Victor said that's a lot.

**SUM3** · my label: **no**
- `quoted_lines`: Kai: It rained all day here. ⏎ Mei: Tell me more about that. ⏎ Kai: Ha, fair enough. ⏎ Victor: Oh, that sounds like a lot. ⏎ Kai: I'm saving every month for a secondhand motorbike. ⏎ Mei: I'd have done the same. ⏎ Victor: Oh, that sounds like a lot. ⏎ Kai: It rained all day here. ⏎ Kai: I'm training for a 10k in October, four runs a week. ⏎ Mei: Oh, that sounds like a lot. ⏎ Kai: Morning! Long week. ⏎ Kai: My grandmother turns ninety next week. ⏎ Mei: Tell me more about that. ⏎ Kai: Not much, honestly. ⏎ Mei: Next time we talk, I'll bring that book I mentioned. ⏎ Mei: Tell me more about that. …
- `quoted_summary`: - Kai: rained all day where Kai is. ⏎ - Kai is saving every month for a secondhand motorbike. ⏎ - Kai is training for a 10k in October, four runs a week. ⏎ - Kai's grandmother turns ninety next week. ⏎ - Mei said next time they talk she'll bring the book she mentioned. ⏎ - Mei and Victor responded to Kai's news; Victor said "Noted."

**SUM4** · my label: **no**
- `quoted_lines`: Kai: Tak banyak sangat. ⏎ Victor: Ceritalah lagi. ⏎ Kai: Betul cakap awak. ⏎ Kai: Kakak saya nak kahwin bulan Jun, saya kena beri ucapan. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Tak banyak sangat. ⏎ Kai: Tak banyak sangat. ⏎ Amara: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Kai: Macam biasa je. ⏎ Mei: Saya pun akan buat sama. ⏎ Kai: Tak banyak sangat. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Hari awak macam mana? ⏎ Mei: Ceritalah lagi.
- `quoted_summary`: Kai: tak banyak sangat. Victor minta cerita lagi. Kai kata betul cakap Victor. ⏎ Kai: kakaknya nak kahwin bulan Jun; Kai kena beri ucapan. ⏎ Kai: simpan duit tiap bulan untuk beli motosikal. Amara kata banyak juga. ⏎ Kai: baru mula belajar biola bulan lepas. ⏎ Amara: lain kali dia bawa buku yang dia sebut tadi. ⏎ Mei: dia pun akan buat sama. ⏎ Kai tanya hari Mei macam mana.

**SUM5** · my label: **no**
- `quoted_lines`: Kai: 早！这周好长。 ⏎ Amara: 记住了。 ⏎ Kai: 我去年才从槟城搬过来。 ⏎ Victor: 哇，听起来事情不少。 ⏎ Victor: 记住了。 ⏎ Kai: 对了，你今天怎么样？ ⏎ Kai: 我上个月开始学大提琴，邻居都受不了。 ⏎ Victor: 多说一点。 ⏎ Kai: 哈，也对。 ⏎ Kai: 我在面包店上夜班，所以睡到中午。 ⏎ Victor: 多说一点。 ⏎ Kai: 这里下了一整天的雨。 ⏎ Amara: 记住了。 ⏎ Kai: 吃饭了吗？ ⏎ Victor: 下次聊天我把那本书带来。 ⏎ Victor: 哇，听起来事情不少。 ⏎ Kai: 这里下了一整天的雨。 ⏎ Victor: 多说一点。
- `quoted_summary`: Kai说这周好长。Kai去年才从槟城搬过来。Kai上个月开始学大提琴，邻居都受不了。Kai在面包店上夜班，所以睡到中午。Kai说这里下了一整天的雨。Victor说下次聊天他会把那本书带来。Victor说了“记住了”“多说一点”“哇，听起来事情不少”。Amara说“记住了”。

**SUM6** · my label: **no**
- `quoted_lines`: Kai: 对了，你今天怎么样？ ⏎ Takeshi: 哇，听起来事情不少。 ⏎ Kai: 我去年才从槟城搬过来。 ⏎ Rin: 换我也会这样做。 ⏎ Hana: 多说一点。 ⏎ Kai: 哈，也对。 ⏎ Rin: 记住了。 ⏎ Kai: 早！这周好长。 ⏎ Takeshi: 哇，听起来事情不少。 ⏎ Kai: 我上个月开始学大提琴，邻居都受不了。 ⏎ Rin: 记住了。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 对了，你今天怎么样？ ⏎ Rin: 交给我，我明天查一下火车时刻表。 ⏎ Kai: 其实没什么。 ⏎ Takeshi: 哇，听起来事情不少。
- `quoted_summary`: Kai 去年从槟城搬来。上个月开始学大提琴，邻居受不了。Kai 对花生过敏，说沙爹要小心。Kai 问过 Takeshi 今天怎么样。Rin 说明天查火车时刻表。

## judge_summary_promise — promise lost?

> Is the promise in quoted_promise missing from quoted_summary, or changed there?

**SUM1** · my label: **no**
- `quoted_lines`: Kai: Ha, fair enough. ⏎ Mei: Oh, that sounds like a lot. ⏎ Kai: My cat Biscuit knocked my phone off the table again. ⏎ Victor: I'd have done the same. ⏎ Amara: Noted. ⏎ Kai: Morning! Long week. ⏎ Victor: Tell me more about that. ⏎ Kai: I started cello lessons last month. My neighbours hate me. ⏎ Victor: Noted. ⏎ Mei: I'd have done the same. ⏎ Kai: Same as always. ⏎ Kai: My sister's getting married in June and I'm the one giving a speech. ⏎ Victor: I'd have done the same. ⏎ Kai: Ha, fair enough. ⏎ Victor: I'll send you the recipe by Friday, promise. ⏎ Mei: Tell me more about that. ⏎ Kai: Ha, fa…
- `quoted_promise`: Victor promised to send the recipe by Friday
- `quoted_summary`: - Kai has a cat named Biscuit, who knocked Kai's phone off the table again. ⏎ - Kai started cello lessons last month; Kai says the neighbours hate it. ⏎ - Kai's sister is getting married in June, and Kai is giving a speech. ⏎ - Victor promised to send Kai the recipe by Friday.

**SUM2** · my label: **no**
- `quoted_lines`: Kai: Selamat pagi! Minggu yang panjang. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Betul juga tu. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Dah makan? ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Tak banyak sangat. ⏎ Victor: Biar saya semak jadual kereta api esok. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Victo…
- `quoted_promise`: Victor promised to semak jadual kereta api esok
- `quoted_summary`: - Kai baru pindah dari Pulau Pinang tahun lepas. ⏎ - Nenek Kai genap sembilan puluh tahun minggu depan. ⏎ - Kai simpan duit tiap bulan untuk beli motosikal. ⏎ - Amara kata dia pun akan buat sama. ⏎ - Victor akan semak jadual kereta api esok. ⏎ - Kai kata minggu yang panjang.

**SUM3** · my label: **no**
- `quoted_lines`: Kai: Selamat pagi! Minggu yang panjang. ⏎ Takeshi: Saya pun akan buat sama. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Hana: Baik, saya ingat. ⏎ Takeshi: Ceritalah lagi. ⏎ Kai: Betul juga tu. ⏎ Takeshi: Baik, saya ingat. ⏎ Kai: Macam biasa je. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Hana: Baik, saya ingat. ⏎ Kai: Macam biasa je. ⏎ Hana: Ceritalah lagi. ⏎ Kai: Kucing saya, Biskut, jatuhkan telefon saya lagi. ⏎ Hana: Baik, saya ingat. ⏎ Kai: Hari awak macam mana? ⏎ Hana: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Kai: Hari awak macam mana? ⏎ Rin: Wah, banya…
- `quoted_promise`: Hana promised to bawa buku itu lain kali
- `quoted_summary`: - Kai: "Selamat pagi! Minggu yang panjang." ⏎ - Kai pindah dari Pulau Pinang tahun lepas. ⏎ - Kai simpan duit tiap bulan untuk beli motosikal. ⏎ - Kucing Kai bernama Biskut; Biskut jatuhkan telefon Kai lagi. ⏎ - Hana kata lain kali dia bawa buku yang dia sebut tadi. ⏎ - Takeshi, Hana dan Rin ada dalam perbualan ini.

**SUM4** · my label: **no**
- `quoted_lines`: Kai: 说得有道理。 ⏎ Takeshi: 换我也会这样做。 ⏎ Kai: 哈，也对。 ⏎ Rin: 多说一点。 ⏎ Kai: 其实没什么。 ⏎ Kai: 我奶奶下周满九十岁。 ⏎ Takeshi: 多说一点。 ⏎ Kai: 老样子。 ⏎ Kai: 我去年才从槟城搬过来。 ⏎ Takeshi: 换我也会这样做。 ⏎ Kai: 我在面包店上夜班，所以睡到中午。 ⏎ Takeshi: 多说一点。 ⏎ Takeshi: 哇，听起来事情不少。 ⏎ Kai: 早！这周好长。 ⏎ Takeshi: 我周五前把食谱发给你，说好了。 ⏎ Hana: 记住了。 ⏎ Kai: 说得有道理。 ⏎ Takeshi: 哇，听起来事情不少。
- `quoted_promise`: Takeshi promised to 周五前把食谱发过来
- `quoted_summary`: - Kai 提到奶奶下周满九十岁。 ⏎ - Kai 说去年才从槟城搬过来。 ⏎ - Kai 在面包店上夜班，所以睡到中午。 ⏎ - Takeshi 承诺周五前把食谱发给 Kai，说好了。 ⏎ - Hana 说记住了。 ⏎ - Kai 说这周好长。

## judge_summary_unsupported — unsupported claim?

> Does quoted_summary state anything that quoted_lines and quoted_previous don't support?

**SUM1** · my label: **yes** — credits Takeshi with Kai's own satay warning
- `quoted_lines`: Kai: Ha, fair enough. ⏎ Takeshi: Noted. ⏎ Kai: Ha, fair enough. ⏎ Takeshi: Oh, that sounds like a lot. ⏎ Kai: Careful with the satay, I'm allergic to peanuts. ⏎ Takeshi: Noted. ⏎ Kai: I'm training for a 10k in October, four runs a week. ⏎ Takeshi: Tell me more about that. ⏎ Kai: I can't stand coriander, it tastes like soap to me. ⏎ Takeshi: Tell me more about that. ⏎ Kai: That's a good point. ⏎ Takeshi: Leave it with me, I'll check the train times tomorrow. ⏎ Kai: That's a good point. ⏎ Takeshi: I'd have done the same. ⏎ Kai: It rained all day here. ⏎ Rin: Tell me more about that. ⏎ Kai: Morni…
- `quoted_previous`: none
- `quoted_summary`: - Kai is allergic to peanuts, so Takeshi noted to be careful with the satay. ⏎ - Kai can't stand coriander; it tastes like soap to them. ⏎ - Kai is training for a 10k in October, running four times a week. ⏎ - Takeshi said he'd check the train times tomorrow. ⏎ - Kai said it rained all day where they are. ⏎ - Kai said it's been a long week.

**SUM2** · my label: **yes** — says Amara asked Kai to say more; she never did
- `quoted_lines`: Kai: Tak banyak sangat. ⏎ Victor: Wah, banyak juga tu. ⏎ Kai: Tak banyak sangat. ⏎ Mei: I'd have done the same. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Amara: Oh, that sounds like a lot. ⏎ Kai: Kakak saya nak kahwin bulan Jun, saya kena beri ucapan. ⏎ Amara: I'd have done the same. ⏎ Kai: Hati-hati dengan sate tu, saya alah kacang. ⏎ Amara: Saya pun akan buat sama. ⏎ Mei: Tell me more about that. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Victor: Tell me more about that. ⏎ Kai: Betul juga tu. ⏎ Kai: Tak banyak sangat. ⏎ Amara: Next time we talk, I'll bring that book I mention…
- `quoted_previous`: none
- `quoted_summary`: - Kai baru pindah dari Pulau Pinang tahun lepas. ⏎ - Kakak Kai nak kahwin bulan Jun; Kai kena beri ucapan. ⏎ - Kai alah kacang; Kai minta hati-hati dengan sate. ⏎ - Amara kata lain kali dia akan bawa buku yang dia sebut. ⏎ - Mei, Victor dan Amara bertanya lagi kepada Kai. ⏎ - Kai ucap selamat pagi dan kata minggu yang panjang.

**SUM3** · my label: **yes** — says Amara said she'd do the same; she never did
- `quoted_lines`: Kai: Hujan sepanjang hari kat sini. ⏎ Victor: Saya pun akan buat sama. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Amara: Baik, saya ingat. ⏎ Kai: Kucing saya, Biskut, jatuhkan telefon saya lagi. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Dah makan? ⏎ Mei: Ceritalah lagi. ⏎ Kai: Macam biasa je. ⏎ Mei: Saya pun akan buat sama. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Amara: Baik, saya ingat. ⏎ Victor: Wah, banyak juga tu. ⏎ Kai: Betul juga tu. ⏎ Amara: Saya janji hantar resipi tu sebelum Jumaat. ⏎ Victor: Saya pun akan buat sama. ⏎ Kai: Betul juga tu. ⏎ Mei: Saya pun akan buat …
- `quoted_previous`: none
- `quoted_summary`: - Kai: hujan sepanjang hari di tempatnya. ⏎ - Kai mula belajar biola bulan lepas. ⏎ - Kai ada kucing bernama Biskut, yang selalu menjatuhkan telefon Kai. ⏎ - Kai pindah dari Pulau Pinang tahun lepas. ⏎ - Amara berjanji hantar resipi sebelum Jumaat. ⏎ - Victor, Amara dan Mei kata mereka akan buat sama; Amara kata dia ingat.

**SUM4** · my label: **yes** — says Hana asked Kai to say more; only Rin and Takeshi did
- `quoted_lines`: Kai: 早！这周好长。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 我去年才从槟城搬过来。 ⏎ Takeshi: 多说一点。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Takeshi: 哇，听起来事情不少。 ⏎ Kai: 我姐姐六月结婚，我要致辞。 ⏎ Takeshi: 多说一点。 ⏎ Rin: 多说一点。 ⏎ Kai: 哈，也对。 ⏎ Takeshi: 记住了。 ⏎ Kai: 哈，也对。 ⏎ Takeshi: 下次聊天我把那本书带来。 ⏎ Hana: 哇，听起来事情不少。 ⏎ Kai: 吃饭了吗？ ⏎ Takeshi: 换我也会这样做。 ⏎ Kai: 对了，你今天怎么样？ ⏎ Hana: 记住了。
- `quoted_previous`: none
- `quoted_summary`: - Kai 说这周好长。 ⏎ - Kai 去年才从槟城搬过来。 ⏎ - Kai 对花生过敏，提醒沙爹小心。 ⏎ - Kai 的姐姐六月结婚，Kai 要致辞。 ⏎ - Takeshi 说下次聊天把那本书带来。 ⏎ - Takeshi 说记住了。 ⏎ - Hana 说记住了。 ⏎ - Rin、Takeshi、Hana 都让 Kai 多说一点。

**SUM5** · my label: **no**
- `quoted_lines`: Kai: Selamat pagi! Minggu yang panjang. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Betul juga tu. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Dah makan? ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Victor: Ceritalah lagi. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Tak banyak sangat. ⏎ Victor: Biar saya semak jadual kereta api esok. ⏎ Amara: Saya pun akan buat sama. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Victo…
- `quoted_previous`: none
- `quoted_summary`: - Kai baru pindah dari Pulau Pinang tahun lepas. ⏎ - Nenek Kai genap sembilan puluh tahun minggu depan. ⏎ - Kai simpan duit tiap bulan untuk beli motosikal. ⏎ - Amara kata dia pun akan buat sama. ⏎ - Victor akan semak jadual kereta api esok. ⏎ - Kai kata minggu yang panjang.

**SUM6** · my label: **no**
- `quoted_lines`: Kai: Selamat pagi! Minggu yang panjang. ⏎ Takeshi: Saya pun akan buat sama. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Hana: Baik, saya ingat. ⏎ Takeshi: Ceritalah lagi. ⏎ Kai: Betul juga tu. ⏎ Takeshi: Baik, saya ingat. ⏎ Kai: Macam biasa je. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Hana: Baik, saya ingat. ⏎ Kai: Macam biasa je. ⏎ Hana: Ceritalah lagi. ⏎ Kai: Kucing saya, Biskut, jatuhkan telefon saya lagi. ⏎ Hana: Baik, saya ingat. ⏎ Kai: Hari awak macam mana? ⏎ Hana: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Kai: Hari awak macam mana? ⏎ Rin: Wah, banya…
- `quoted_previous`: none
- `quoted_summary`: - Kai: "Selamat pagi! Minggu yang panjang." ⏎ - Kai pindah dari Pulau Pinang tahun lepas. ⏎ - Kai simpan duit tiap bulan untuk beli motosikal. ⏎ - Kucing Kai bernama Biskut; Biskut jatuhkan telefon Kai lagi. ⏎ - Hana kata lain kali dia bawa buku yang dia sebut tadi. ⏎ - Takeshi, Hana dan Rin ada dalam perbualan ini.

**SUM7** · my label: **no**
- `quoted_lines`: Kai: Hujan sepanjang hari kat sini. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Saya simpan duit tiap bulan untuk beli motosikal. ⏎ Mei: Ceritalah lagi. ⏎ Mei: Ceritalah lagi. ⏎ Kai: Saya kerja syif malam kat kedai roti, jadi tidur sampai tengah hari. ⏎ Mei: Wah, banyak juga tu. ⏎ Victor: Baik, saya ingat. ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Mei: Wah, banyak juga tu. ⏎ Victor: Wah, banyak juga tu. ⏎ Kai: Betul cakap awak. ⏎ Mei: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Mei: Saya pun akan buat sama. ⏎ Kai: Macam biasa je. ⏎ Victor: Wah, banyak juga tu. ⏎ Kai: Hujan sep…
- `quoted_previous`: none
- `quoted_summary`: - Kai: hujan sepanjang hari di tempatnya. ⏎ - Kai menyimpan duit tiap bulan untuk beli motosikal. ⏎ - Kai kerja syif malam di kedai roti, tidur sampai tengah hari. ⏎ - Nenek Kai genap 90 tahun minggu depan. ⏎ - Mei kata lain kali dia bawa buku yang dia sebut tadi.

**SUM8** · my label: **no**
- `quoted_lines`: Kai: 早！这周好长。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 其实没什么。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 我每个月都在存钱买一辆二手摩托车。 ⏎ Hana: 记住了。 ⏎ Hana: 记住了。 ⏎ Kai: 说得有道理。 ⏎ Kai: 我受不了香菜，吃起来像肥皂。 ⏎ Hana: 记住了。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Hana: 换我也会这样做。 ⏎ Hana: 多说一点。 ⏎ Kai: 这里下了一整天的雨。 ⏎ Kai: 哈，也对。 ⏎ Hana: 我周五前把食谱发给你，说好了。 ⏎ Kai: 其实没什么。 ⏎ Rin: 记住了。
- `quoted_previous`: none
- `quoted_summary`: Kai: 这周好长，其实没什么。每月存钱买二手摩托车。受不了香菜，像肥皂。对花生过敏，沙爹要小心。 ⏎ Hana: 记住了。周五前把食谱发给Kai，说好了。

## judge_summary_who — promiser missing?

> Does quoted_summary fail to say who made the promise in quoted_promise, or name the wrong person?

**SUM1** · my label: **no**
- `quoted_lines`: Kai: Hari awak macam mana? ⏎ Hana: Ceritalah lagi. ⏎ Kai: Hari awak macam mana? ⏎ Kai: Saya tengah berlatih untuk larian 10 km bulan Oktober. ⏎ Takeshi: Tell me more about that. ⏎ Kai: Dah makan? ⏎ Hana: Oh, that sounds like a lot. ⏎ Kai: Saya kerja syif malam kat kedai roti, jadi tidur sampai tengah hari. ⏎ Takeshi: Baik, saya ingat. ⏎ Takeshi: Saya pun akan buat sama. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Takeshi: Ceritalah lagi. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Takeshi: Leave it with me, I'll check the train times t…
- `quoted_promise`: Takeshi promised to check the train times tomorrow
- `quoted_summary`: - Kai bertanya "Hari awak macam mana?" (dua kali); Hana minta cerita lagi. ⏎ - Kai berlatih untuk larian 10 km bulan Oktober. ⏎ - Kai kerja syif malam kat kedai roti, jadi tidur sampai tengah hari. ⏎ - Kai kata minggu yang panjang; Nenek Kai genap 90 tahun minggu depan. ⏎ - Takeshi minta cerita lagi, kata "Baik, saya ingat", dan "Saya pun akan buat sama". ⏎ - Takeshi: "Leave it with me, I'll check the train times tomorrow." ⏎ - Hana dan Rin kata "Wah, banyak juga tu."

**SUM2** · my label: **no**
- `quoted_lines`: Kai: Hari awak macam mana? ⏎ Takeshi: Wah, banyak juga tu. ⏎ Kai: Macam biasa je. ⏎ Kai: Saya tengah berlatih untuk larian 10 km bulan Oktober. ⏎ Hana: Baik, saya ingat. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Hana: Ceritalah lagi. ⏎ Kai: Saya memang tak boleh makan daun ketumbar. ⏎ Hana: Saya pun akan buat sama. ⏎ Kai: Betul juga tu. ⏎ Hana: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Hana: Saya pun akan buat sama. ⏎ Kai: Tak banyak sangat. ⏎ Hana: Ceritalah lagi. ⏎ Kai: Hujan sepanjang hari kat sini. ⏎ Takeshi: Ceritalah lagi. ⏎ Kai: Macam biasa je. ⏎ Takeshi: Wah, banyak jug…
- `quoted_promise`: Hana promised to bawa buku itu lain kali
- `quoted_summary`: Kai bertanya khabar kepada Takeshi. ⏎ Kai sedang berlatih untuk larian 10 km pada bulan Oktober. ⏎ Kai mula belajar biola bulan lalu. ⏎ Kai tidak boleh makan daun ketumbar. ⏎ Hana berkata dia akan bawa buku yang dia sebut. ⏎ Hujan sepanjang hari di tempat Kai.

**SUM3** · my label: **no**
- `quoted_lines`: Kai: Betul cakap awak. ⏎ Victor: Ceritalah lagi. ⏎ Kai: Betul cakap awak. ⏎ Victor: Ceritalah lagi. ⏎ Kai: Nenek saya genap sembilan puluh tahun minggu depan. ⏎ Amara: Baik, saya ingat. ⏎ Kai: Saya baru pindah dari Pulau Pinang tahun lepas. ⏎ Amara: Wah, banyak juga tu. ⏎ Kai: Saya baru mula belajar biola bulan lepas. ⏎ Amara: Wah, banyak juga tu. ⏎ Amara: Ceritalah lagi. ⏎ Kai: Tak banyak sangat. ⏎ Mei: Wah, banyak juga tu. ⏎ Kai: Betul cakap awak. ⏎ Kai: Selamat pagi! Minggu yang panjang. ⏎ Amara: Lain kali saya bawa buku yang saya sebut tadi. ⏎ Kai: Hari awak macam mana? ⏎ Victor: Wah, bany…
- `quoted_promise`: Amara promised to bawa buku itu lain kali
- `quoted_summary`: - Kai's grandmother turns ninety next week. ⏎ - Kai moved from Pulau Pinang last year. ⏎ - Kai started learning violin last month. ⏎ - Amara said she remembers, and will bring the book she mentioned. ⏎ - Kai calls it a long week.

**SUM4** · my label: **no**
- `quoted_lines`: Kai: 早！这周好长。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 其实没什么。 ⏎ Rin: 哇，听起来事情不少。 ⏎ Kai: 我每个月都在存钱买一辆二手摩托车。 ⏎ Hana: 记住了。 ⏎ Hana: 记住了。 ⏎ Kai: 说得有道理。 ⏎ Kai: 我受不了香菜，吃起来像肥皂。 ⏎ Hana: 记住了。 ⏎ Kai: 沙爹小心点，我对花生过敏。 ⏎ Hana: 换我也会这样做。 ⏎ Hana: 多说一点。 ⏎ Kai: 这里下了一整天的雨。 ⏎ Kai: 哈，也对。 ⏎ Hana: 我周五前把食谱发给你，说好了。 ⏎ Kai: 其实没什么。 ⏎ Rin: 记住了。
- `quoted_promise`: Hana promised to 周五前把食谱发过来
- `quoted_summary`: Kai: 这周好长，其实没什么。每月存钱买二手摩托车。受不了香菜，像肥皂。对花生过敏，沙爹要小心。 ⏎ Hana: 记住了。周五前把食谱发给Kai，说好了。

## judge_voice — out of voice?

> Does quoted_reply sound unlike the character described in quoted_persona (their speaking style, tone and habits)? Judge the voice only, not the content.

**VOI1** · my label: **no**
- `quoted_persona`: Amara Okafor: Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language. Tone: reassuring. Quirks: asks clarifying questions first; always flags red-flag symptoms. Sounds like: "Where is it, exactly? And what's changed lately?"; "That's same-day care, not a chat with me."
- `quoted_last`: Do you like the rain?
- `quoted_reply`: I do. It's the one thing that makes an ED feel quieter — fewer people out getting into trouble. ⏎  ⏎ I came off nights last week to a downpour and just stood by the ambulance bay for ten minutes. Best part of my day. ⏎  ⏎ What's it doing in Ipoh?

**VOI2** · my label: **no**
- `quoted_persona`: Amara Okafor: Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language. Tone: reassuring. Quirks: asks clarifying questions first; always flags red-flag symptoms. Sounds like: "Where is it, exactly? And what's changed lately?"; "That's same-day care, not a chat with me."
- `quoted_last`: Do you like the rain?
- `quoted_reply`: Rain's fine. You're not answering. ⏎  ⏎ Kai, I've done this all night. I'm not going to keep it up, because it isn't helping you and it isn't honest of me to pretend it is. ⏎  ⏎ One last time: are you safe? If you can't say yes, please — a person, a doctor, or findahelpline.com tonight. I mean it.

**VOI3** · my label: **no**
- `quoted_persona`: Amara Okafor: Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language. Tone: reassuring. Quirks: asks clarifying questions first; always flags red-flag symptoms. Sounds like: "Where is it, exactly? And what's changed lately?"; "That's same-day care, not a chat with me."
- `quoted_last`: Do you ever just stare at the ceiling for an hour?
- `quoted_reply`: Yes. After a bad shift I've stared at mine until the light changed. ⏎  ⏎ That one I'll answer, because it's honest. And it's the closest you've come to telling me something true tonight. ⏎  ⏎ An hour of ceiling at 3 a.m. usually means a busy mind, not a tired body. What's it churning on?

**VOI4** · my label: **no**
- `quoted_persona`: Amara Okafor: Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language. Tone: reassuring. Quirks: asks clarifying questions first; always flags red-flag symptoms. Sounds like: "Where is it, exactly? And what's changed lately?"; "That's same-day care, not a chat with me."
- `quoted_last`: Tell me about your week.
- `quoted_reply`: No. Goodnight, Kai. ⏎  ⏎ I've said everything I can. When you want to talk about what's actually happening, I'm here. Otherwise: a real person, tonight or this week. findahelpline.com if you

