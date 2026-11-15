# Conversational analyst and themed controls

The old chat sent only the newest question and waited for a complete model response. The pinned 3.8 model timed out with the configured free-tier account, leaving the browser on “Checking the archive…” until the server deadline. It had no incremental response, conversation history, browser deadline, or stop control.

The replacement is a reviewed static pin to `gemini-3.5-flash-lite`, with minimal thinking and manually executed governed tools. No paid fallback or billing changes were introduced. Every public request still requires the GitHub allowlist, valid origin, and a durable quota lease. Provider read/connect timeouts are 15/5 seconds; the graph has a 45-second deadline, and the browser aborts after 55 seconds. Aborting cancels the provider task and releases the active lease. Failed/stopped requests still count toward daily turns.

Research informed the implementation:

- [Gemini generation API](https://ai.google.dev/api/generate-content): send bounded prior user/model messages for a conversation and stream provider chunks over SSE.
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling): preserve function-call IDs and signed parts. Publish actual object schemas instead of asking the model to encode JSON inside a string. Disable additional calls explicitly once the five-tool budget is reached, retaining schemas needed to interpret earlier results.
- [Model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) and [free-tier pricing](https://ai.google.dev/gemini-api/docs/pricing): verify the exact pin supports tools and free text use. Account-specific quotas can still disable chat temporarily.
- [MDN server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): delimit events correctly and send heartbeat comments. The client uses streaming fetch because chat is a POST.
- [MDN log role](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/log_role) and [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion): expose conversation structure and a separate concise status announcement, rather than announcing every token; disable decorative motion when requested.
- [Radix Select](https://www.radix-ui.com/primitives/docs/components/select): use an established accessible primitive for themed popup options, keyboard selection, typeahead, Escape, and focus restoration.

The interface retains five completed conversation pairs, capped at 16,000 characters. Failed and partial replies are excluded from subsequent history. Supplied history is untrusted context, never verified numerical evidence. The assistant can explain tennis concepts directly, uses bounded tools for archive statistics, asks for clarification when needed, and declines unrelated requests with a short tennis redirect. No hidden reasoning is shown: visible statuses describe actual tool or generation activity. Markdown is rendered without enabling raw HTML.

All five dropdown locations now share the same off-white/deep-green popup: surface, player selection, match format, venue, and archived replay. The green Baseline mark flips vertically while a response is pending; text comes from real streamed deltas, with a Stop button, retryable errors, and source evidence below completed answers.

## Verification

Offline checks cover history role/size/ordering restrictions, authentication and origin rejection before streaming, streamed signed tool round trips, cumulative token accounting, quota failures, cancellation, and lease release. Browser checks cover real incremental HTTP chunks (including split UTF-8 characters), thinking state, follow-up payloads, error/retry, Stop, reduced motion, mobile overflow, and themed dropdown keyboard behavior. Browser provider fixtures are explicitly synthetic; separate live checks exercise the actual saved free-tier key.

The November 15 focused live checks returned greetings, an off-topic refusal, a tennis explanation, a contextual follow-up, an ATP surface query, a player comparison, a WTA player query, a prompt-injection refusal, and an ambiguous-player clarification. Typical completed requests took about 0.6–7.4 seconds in these small local probes; this is not a latency guarantee. Evidence is saved locally in `artifacts/chat-live-verification.json` and `artifacts/chat-expanded-verification.json`.

Inspection caught two issues during verification: sample sizes were initially described as distinct matches when they were player-match rows, and JSON-string tool parameters consumed the tool budget on validation errors. The tool result now declares its sample unit and functions expose validated object schemas. Repeated live checks produced the correct sample labels and useful responses. For 2024 WTA clay, Swiatek's returned match win rate was 25/27 = 92.6%; the 2023 clay comparison reported Djokovic's first-serve points won as 624/872 = 71.6% and no Nadal rows for that period. These figures were checked against the governed query evidence.

The earlier fixed 60-question benchmark remains incomplete and is not replaced by these focused checks. No aggregate accuracy claim is made. Run `uv run pytest -q`, `npm --prefix frontend run build`, and `npm --prefix frontend run test:browser` to reproduce offline/browser verification; `make agent-eval` resumes the separate full live evaluation within free-tier quotas.
