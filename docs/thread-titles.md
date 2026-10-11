# Conversation headings

Completed non-private chats receive a short topic heading in the sidebar and history
dialog. The first substantive exchange supplies the topic; greetings use
`New Conversation` until a substantive follow-up arrives. For example,
`write a python code` can become `Python Coding Help`.

The browser saves the thread before requesting its title. A serial queue operates
independently of the search component and uses the exact saved ID. The response
re-reads storage and checks the topic and current title before updating. Navigation,
duplicate prompts, deletion and a late response cannot redirect a title to another
thread. Persistence preserves the title metadata along with conversation content.

Manual renames are marked explicitly and retained. Legacy custom headings are
preserved conservatively because their origin is unknown. Legacy headings equal to
a saved user prompt are replaced with topic headings; up to seven recent entries
are considered for provider generation per history refresh. Reopening a thread also
repairs its heading. This does not rename custom headings or require replaying chat
answers.

`POST /api/v1/search/title` accepts a bounded query and optional answer excerpt.
The generator returns a JSON title with 2–6 words and at most 64 characters. It
rejects empty output, copied prompts, questions, markdown and invalid output.
The request has an eight-second provider deadline and enough output tokens for
reasoning models. Title generation never runs web search or blocks the answer.

Provider errors or invalid output retain a deterministic topic heading. The browser
uses a one-hour retry backoff, reconsidered on later history refreshes or reopening.
Greetings and conversation recall/notes have local headings and do not need a model.
Private mode sends no title requests or title writes; a response already pending is
discarded if private mode becomes active before it arrives.

Validation includes 77 backend tests (104 subtests), 27 frontend tests and the
production build. Browser checks exercise instant/late title responses, refresh,
legacy history and an open history dialog, duplicate prompts, manual rename,
greeting-to-topic updates, provider failure/backoff and private mode. A real chat
note and its local heading are saved together. The browser regression also covers
the research indicator's empty-to-streaming transition, which previously violated
React's hook order and could crash follow-ups.

Titles and history continue to be saved in this browser. Cross-device or shared
team persistence is outside this change. Provider-generated wording can vary;
the heading's topic and limits are enforced.
