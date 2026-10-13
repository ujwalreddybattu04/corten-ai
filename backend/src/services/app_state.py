"""Answer selection-state questions from this request, never from search or history.

Match whole questions so an external or mixed request still reaches normal routing.
The selected response mode is distinct from the model Auto may choose for an answer.
"""
import re

from src.services.chat_context import TurnContext

_SUBJECT = r"(?:(?:answer|response|chat|thinking|focus) )?(?:mode|model)"
_TAIL = r"(?: (?:now|right now|currently|here|today|for this (?:chat|question)|in (?:this chat|corten)))*"
_PATTERNS = tuple(re.compile(pattern + _TAIL) for pattern in (
    rf"(?:what|which) {_SUBJECT} (?:have i|did i|i|we) (?:select(?:ed)?|choose|chosen|picked|pick)",
    rf"(?:what|which) {_SUBJECT} (?:(?:is|has been) )?(?:currently )?(?:selected|chosen|active|enabled)",
    rf"(?:what|which) {_SUBJECT} do i have (?:selected|chosen|enabled)",
    rf"(?:what|which) {_SUBJECT} (?:am i|are we|are you) (?:using|in|on)",
    rf"(?:what|which) {_SUBJECT} (?:is selected|am i using|are you using) (?:in this app|in corten)",
    rf"(?:what is|what s|whats|which is) (?:my|our|the) (?:current |selected |active )?{_SUBJECT}",
    rf"(?:my|our|the) (?:current |selected |active ){_SUBJECT}",
    r"(?:am i|are we) (?:in|on|using) (?:auto|fast|pro|extended thinking|thinking)(?: mode)?",
    r"is (?:auto|fast|pro|extended thinking|thinking)(?: mode)? (?:selected|active|enabled)",
))


def selection_question(query: str) -> bool:
    if len(query) > 350:
        return False
    text = re.sub(r"[?’'?!.،,]+", " ", query.casefold()).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(?:please )?(?:(?:can|could) (?:you|u) )?(?:please )?"
                  r"(?:(?:tell|show) me )?", "", text).strip()
    return any(pattern.fullmatch(text) for pattern in _PATTERNS)


def selection_answer(query: str, turn: TurnContext, focus_mode: str = "all") -> str | None:
    if not selection_question(query):
        return None
    # Focus controls (All, Academic, Writing, ...) are a different selector. Do not
    # misreport a response mode when the question explicitly asks for focus state.
    if re.search(r"\bfocus\b", query, re.IGNORECASE):
        focus = {"all": "All", "academic": "Academic", "code": "Code", "writing": "Writing",
                 "math": "Math", "reddit": "Reddit", "youtube": "YouTube", "social": "Social"}.get(focus_mode)
        return (f"Your focus mode is **{focus}** for this message." if focus else
                "I can't confirm the selected focus mode from this request. Check the focus selector in the composer.")
    label = {"auto": "Auto", "fast": "Fast", "pro": "Pro", "think": "Extended thinking"}.get(turn.mode)
    if label is None:
        return "I can't confirm the selected response mode from this request. Check the mode selector beside the send button."
    answer = f"You have **{label}** selected for this message."
    if turn.mode == "auto":
        answer += " Auto chooses the response model for each question."
    if re.search(r"\bmodel\b", query, re.IGNORECASE):
        answer += " This is your response-mode selection; this answer reads app settings without calling a model."
    return answer
