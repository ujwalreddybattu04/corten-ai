"""Artifacts: substantial, standalone content shown in a side panel (apps, dashboards, diagrams, documents).

The model writes an artifact block in its answer; the frontend renders it in an isolated sandbox
with a self-hosted runtime. Nothing in an artifact can reach the network or the user's session.
"""
import re

OPEN = ":::artifact"
CLOSE = ":::"

REQUEST = re.compile(
    r"\b(?:build|create|make|design|generate|code|develop|prototype|draw|visuali[sz]e|sketch|mock ?up|write)\b.{0,80}?"
    r"\b(?:app|application|dashboard|website|web ?page|landing page|component|game|calculator|tool|ui|interface|"
    r"visuali[sz]ation|chart|graph|diagram|flow ?chart|mind ?map|timeline|org ?chart|sequence diagram|prototype|widget|"
    r"form|simulation|simulator|tracker|planner|quiz|flashcards|interactive|artifact|svg|html|react)\b"
    r"|\bartifact\b|\binteractive\b",
    re.I | re.S)

PROMPT = """
ARTIFACTS: When the user asks you to build something visual or interactive (app, dashboard, chart, diagram, web page,
game, calculator, tool, form) or a substantial standalone piece of content they will reuse, put it in ONE artifact:

:::artifact{type="react" title="Short descriptive title"}
...complete artifact content...
:::

Types:
- react: one self-contained React component file with a default export. You may import only from "react",
  "recharts" (charts) and "lucide-react" (icons). Style with inline styles or a <style> element; Tailwind is not
  available. Keep state with hooks.
- html: a complete self-contained HTML document with inline <style> and <script>.
- mermaid: Mermaid diagram source only (flowchart, sequenceDiagram, classDiagram, gantt, mindmap, timeline, erDiagram).
  Wrap every node label in double quotes, e.g. A["Probation review (30 days)"], and avoid quotes inside labels.
- svg: one complete <svg> element.
- markdown: a long document (report, plan, proposal) the user will copy or download.
- code: a standalone program or script; add language, e.g. :::artifact{type="code" language="python" title="..."}

Rules: artifacts run in a sandbox with NO network access, so never load external scripts, fonts, images or APIs;
embed data inline. Make it polished and production quality: clear layout, accessible labels, responsive sizing,
realistic sample data unless the user supplied data (then use theirs exactly). Write one short sentence before the
artifact and a brief summary of what it does after it. Do not wrap the artifact in code fences. To change an existing
artifact, output the full updated artifact again with the same title. Answer simple questions normally, without an
artifact.
"""


def requested(query: str) -> bool:
    return bool(REQUEST.search(query or ""))


def inside_open_artifact(text: str) -> bool:
    """True while the streamed answer is inside an artifact block (its content must never be cut)."""
    opened = text.rfind(OPEN)
    if opened < 0:
        return False
    return not re.search(r"\n:::\s*(?:\n|$)", text[opened + len(OPEN):])
