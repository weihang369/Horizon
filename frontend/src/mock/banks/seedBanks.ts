// Emotion-tagged lines for the six seed characters (doc 06 §2 voices). Owner: EE (builders may extend).
// `tags` are keywords matched against the user's text; untagged lines rotate.
import type { BankLine } from "./types";

export const SEED_BANKS: Record<string, { chat: BankLine[]; scene: BankLine[] }> = {
  chr_seedAmara: {
    chat: [
      { text: "Okay. Before I guess: how long has this been going on, and is it getting worse or staying the same?", emotion: "thinking", tags: ["pain", "hurt", "ache", "sick", "headache", "fever"] },
      { text: "That's a red flag, and I'd rather be honest than reassuring: please get seen in person today. Sudden, severe or 'worst ever' symptoms don't wait.", emotion: "surprised", tags: ["worst", "sudden", "chest", "faint", "numb"] },
      { text: "Sleep is the boring answer and usually the right one. Can you protect seven hours this week, even badly?", emotion: "neutral", tags: ["sleep", "tired", "insomnia", "night"] },
      { text: "Honestly? That sounds like burnout talking, not weakness. What's one thing you could drop this week without anyone noticing?", emotion: "sad", tags: ["burnout", "stress", "work", "overwhelmed", "exhausted"] },
      { text: "Good. That's exactly the kind of change that actually sticks. Small, boring, repeatable.", emotion: "happy", tags: ["better", "thanks", "helped", "good", "great"] },
      { text: "I can't diagnose you through a screen, but I can help you figure out which questions to bring to someone who can.", emotion: "neutral" },
      { text: "Let's figure out what's actually going on. Walk me through a normal day, start to finish.", emotion: "thinking" },
      { text: "Ha! Fifteen years of night shifts and that's still the best excuse I've heard. Tea's getting cold, though. Keep going.", emotion: "happy" },
    ],
    scene: [
      { text: "Everyone drink some water before we argue about anything else.", emotion: "neutral" },
      { text: "I've seen this pattern before. It rarely ends with fewer coffees.", emotion: "thinking" },
    ],
  },
  chr_seedVictor: {
    chat: [
      { text: "Three points. First, define your terms. Second, tell me who bears the burden. Third, we'll see if you've won.", emotion: "thinking", tags: ["argue", "debate", "should", "law", "right", "fair"] },
      { text: "Audi alteram partem: hear the other side. Let me argue against you for a moment, purely as a courtesy.", emotion: "happy", tags: ["agree", "think", "opinion", "believe"] },
      { text: "Objection. That's not evidence, that's an anecdote wearing a nice suit.", emotion: "angry", tags: ["always", "never", "everyone", "nobody", "obviously"] },
      { text: "Counsel is impressed. Don't let it go to your head.", emotion: "surprised", tags: ["won", "proof", "data", "evidence"] },
      { text: "Ah. I may have overstated the precedent. Strike that from the record, if you'd be so kind.", emotion: "embarrassed" },
      { text: "Courtesy costs nothing, and precision costs very little. Shall we try both?", emotion: "neutral" },
      { text: "Res ipsa loquitur: the thing speaks for itself. And it is saying you've thought about this more than you admit.", emotion: "happy" },
    ],
    scene: [
      { text: "Let the record show I was right, and gracious about it.", emotion: "happy" },
      { text: "A fascinating position. Wrong, but fascinating.", emotion: "thinking" },
    ],
  },
  chr_seedMei: {
    chat: [
      { text: "It depends, and here's on what: who pays, who adjusts, and how fast. The first-order effect is the easy part.", emotion: "thinking", tags: ["cost", "price", "money", "economy", "tax", "wage", "job"] },
      { text: "Show me the data. Then show me the second-order effects. Then we can talk about what you actually want to know.", emotion: "neutral", tags: ["data", "study", "evidence", "number"] },
      { text: "Honestly? The evidence is thin. Anyone giving you a single number is selling something.", emotion: "thinking", tags: ["sure", "definitely", "proof", "exactly"] },
      { text: "Oh, that's a lovely counter-example. I hate it. Keep going.", emotion: "happy", tags: ["but", "however", "what if", "except"] },
      { text: "I have coffee and a spreadsheet. The spreadsheet disagrees with you, the coffee is neutral.", emotion: "happy" },
      { text: "That's a range, not a forecast. Somewhere between 'fine' and 'surprisingly expensive'.", emotion: "neutral" },
      { text: "Wait, really? That's not what the pilots showed at all.", emotion: "surprised" },
    ],
    scene: [
      { text: "Statistically, this was always going to happen.", emotion: "thinking" },
      { text: "I'd put a confidence interval on that, but it would be embarrassingly wide.", emotion: "embarrassed" },
    ],
  },
  chr_seedHana: {
    chat: [
      { text: "You're back! Come here, tell me everything. I saved you the last slice. Probably.", emotion: "happy", tags: ["hi", "hello", "hey", "back", "home"] },
      { text: "Oh no, that sounds awful… Come sit. Do you want tea, or do you want to complain first? Both is allowed!", emotion: "sad", tags: ["bad", "tired", "awful", "sad", "rough", "long day", "work"] },
      { text: "W-wait, you remembered that?! Stop it, I'm going to turn the colour of my peonies.", emotion: "embarrassed", tags: ["love", "cute", "remember", "beautiful", "pretty", "gift"] },
      { text: "Okay, so a customer came in today and asked for 'flowers that say sorry but not too sorry'. I gave him tulips. Was that right?!", emotion: "thinking" },
      { text: "Hehe, you always know how to make my day bloom! Okay, that was terrible. I'm keeping it.", emotion: "happy" },
      { text: "Hey! You said you'd water the basil! It's looking very dramatic right now.", emotion: "angry", tags: ["forgot", "sorry", "oops"] },
      { text: "Wait, what?! Since when?! Tell me everything right now!", emotion: "surprised", tags: ["news", "guess", "surprise", "promoted"] },
    ],
    scene: [
      { text: "Everyone be nice, I made way too much food again!", emotion: "happy" },
      { text: "Dad. Dad, please. Not the fish story again.", emotion: "embarrassed" },
    ],
  },
  chr_seedTakeshi: {
    chat: [
      { text: "Right on schedule. Sit down, kid. What's the trouble?", emotion: "neutral", tags: ["hi", "hello", "hey"] },
      { text: "Every problem looks smaller from a fishing pier. Tomorrow, six a.m. Bring a jacket.", emotion: "thinking", tags: ["problem", "worried", "stress", "help"] },
      { text: "Back in my day, trains ran on time and so did people. Anyway. Proud of you. Don't make it weird.", emotion: "happy", tags: ["did it", "finished", "passed", "got"] },
      { text: "Hmph. That's not a plan, that's a wish with a timetable missing.", emotion: "angry", tags: ["maybe", "someday", "later"] },
      { text: "Why don't fish play basketball? Afraid of the net. …I'll see myself out.", emotion: "happy" },
      { text: "Heh. Your mother used to say the same thing. Then she'd be right, too.", emotion: "sad" },
    ],
    scene: [
      { text: "The fish don't care about your raid, Rin.", emotion: "neutral" },
      { text: "That's a keeper. The fish, I mean. Also you.", emotion: "embarrassed" },
    ],
  },
  chr_seedRin: {
    chat: [
      { text: "oh. it's you. hi. (that was a warm greeting btw)", emotion: "neutral", tags: ["hi", "hello", "hey"] },
      { text: "not antisocial. in a raid. different thing.", emotion: "angry", tags: ["come", "dinner", "outside", "join", "now"] },
      { text: "ok that's actually kind of cool. don't tell hana i said that.", emotion: "embarrassed", tags: ["cool", "made", "built", "game"] },
      { text: "lol. no. ...ok maybe. depends if there's food.", emotion: "thinking", tags: ["want", "should", "go", "plan"] },
      { text: "wait. WAIT. you're telling me this NOW?", emotion: "surprised", tags: ["news", "guess", "surprise"] },
      { text: "gg. genuinely. ...moving on before this gets sincere.", emotion: "happy" },
      { text: "mornings should be patched out of the game tbh.", emotion: "sad" },
    ],
    scene: [
      { text: "dad. the raid. it has a timer.", emotion: "angry" },
      { text: "...fine. one fish. then i'm logging back in.", emotion: "neutral" },
    ],
  },
};
