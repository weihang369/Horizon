// Doc 11 S8 (safety D18): the privacy notice, fixed text in two existing places, shown by the mock and the HTTP client
// alike. D-80 routes chats with data collection allowed, which DeepSeek's own endpoint needs; `allow_fallbacks` means
// another full-precision host may serve a request.
export const CONNECTION_NOTICE =
  "Chats go through OpenRouter to DeepSeek (or, if it is unavailable, another full-precision provider) with data collection allowed, which DeepSeek's own endpoint needs. These providers may use what they receive for training: your messages, passages from your documents that a character uses, and memories. Don't share what you need to keep private.";

export const KNOWLEDGE_NOTICE =
  "Each document is sent once to the embedding provider when you add it; passages a character uses go to DeepSeek, which may train on them.";
