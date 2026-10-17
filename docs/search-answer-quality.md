# Search answer quality

Normal Search now has a separate answer policy, applied to direct answers, tool explanations, web answers and Search research synthesis. Space agent prompts, Pharma, company-fact review, image interpretation and artifact generation retain their existing policies.

## Behavior

- The answer sees the complete question, including instructions after the old Fast-mode 1,000-character cutoff. A router rewrite supplies context without replacing the user's language, scope or output format.
- A named opening subject is not treated as a missing conversational reference merely because a later instruction says "keep it short" or "show how it works". This correction is enabled only for Search.
- Answers use a task-appropriate shape: a recommendation and comparison criteria, an ordered investigation, an explanation with an example, a short clarification, or the requested draft itself. Exact user formatting takes priority.
- Auto can select the existing Pro model for multi-part explanations, decisions and diagnostic work. Explicit Fast, Pro and Extended thinking selections still use their existing resolution rules. Simple follow-ups do not trigger the added depth heuristic.
- Evidence allowances are shared across sources. Relevant passages can come from the middle of a document. Source IDs stay stable; unnumbered tool output does not acquire fabricated citations. Source content is encoded as data, outside system instructions.
- Prompts distinguish supported facts, inferences and hypothetical examples, require citations near supported claims, and ask for missing information to be identified rather than invented. Truncated model responses produce an explicit error instead of a success event for an incomplete answer.
- Answers continue to stream directly. There is no extra model-review call that buffers the entire answer before display. Existing provider limits remain in place.

## Research basis

Reviewed the official [OpenAI prompting guide](https://developers.openai.com/api/docs/guides/prompt-engineering), [accuracy guidance](https://developers.openai.com/api/docs/guides/optimizing-llm-accuracy), [reasoning guidance](https://developers.openai.com/api/docs/guides/reasoning-best-practices), [Groq reasoning documentation](https://console.groq.com/docs/reasoning), and [Anthropic grounding guidance](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations). The implementation uses explicit task constraints, relevant source context and empirical response review, without asking the model to reveal its chain of thought.

## Verification and limits

Regression coverage includes long questions, rewritten questions, explicit modes, Space isolation, stable source IDs, middle passages, malformed snippets, source-boundary injection and token exhaustion. The backend suite is the required release check.

A bounded live-provider review covers seven synthetic cases: explanation, comparison, diagnosis, email drafting, missing evidence, conversational simplification, and a long Spanish-format request. Compared with the initial responses, the format request is preserved, drafting avoids an invented availability commitment, and the explanation is shorter. The fixtures and raw outputs remain private local artifacts; they contain no customer conversations.

These checks do not establish universal factual accuracy. Live responses can still overgeneralize technical properties, attach a citation to an inference, or add an unsupported illustrative detail. Source quality, retrieval coverage, model variability and provider capacity remain limitations. This release improves Search behavior; it does not claim a new verified-evidence engine or perfect answers.
