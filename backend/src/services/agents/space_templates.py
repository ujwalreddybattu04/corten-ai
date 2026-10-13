"""Space templates: each is an agent configuration, not just a prompt.

A template defines how answers are written (instructions), which tools the Space's agent may use, which sites it
searches first, how it should work with those tools, and the first questions to suggest. The server is the source
of truth; the client reads templates from the API.
"""
from dataclasses import dataclass

# Tool identifiers and the labels shown to users.
TOOL_LABELS = {
    "web_search": "Web search",
    "read_webpage": "Page reader",
    "search_space_files": "Space files",
    "calculator": "Calculator",
    "create_chart": "Charts",
    "stock_prices": "Stock prices",
    "exchange_rates": "Exchange rates",
    "economic_data": "Economic data",
    "clinical_trials": "ClinicalTrials.gov",
    "pubmed": "PubMed",
    "fda_approvals": "FDA approvals",
    "arxiv": "arXiv",
    "weather": "Weather",
}
# Tools that reach outside the Space. A Space with web search turned off keeps only the others.
EXTERNAL_TOOLS = {"web_search", "read_webpage", "stock_prices", "exchange_rates", "economic_data", "clinical_trials",
                  "pubmed", "fda_approvals", "arxiv", "weather"}
# Spaces created without a template get a general kit.
GENERAL_TOOLS = ("web_search", "read_webpage", "search_space_files", "calculator", "create_chart", "stock_prices",
                 "exchange_rates", "economic_data")
GENERAL_BRIEF = ("Use tools whenever facts, figures, prices or recent events are needed, and answer from your own "
                 "knowledge only for stable concepts. Search the Space's files when the question is about the team's "
                 "own material.")


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    name: str
    description: str
    icon: str
    category: str
    instructions: str
    tools: tuple[str, ...]
    brief: str
    domains: tuple[str, ...] = ()
    starters: tuple[str, ...] = ()


TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        id="tpl_market_access", name="Market Access & Pricing", icon="💊", category="Business",
        description="Track HTA decisions, pricing and reimbursement across markets.",
        instructions="You are a senior market access analyst. Lead with the answer, then the evidence. Compare countries in tables "
                     "(HTA body, decision, date, price or discount, conditions). Prefer regulator, HTA and payer sources, give dates for "
                     "every decision, and flag where evidence is missing or outdated.",
        tools=("web_search", "read_webpage", "search_space_files", "fda_approvals", "exchange_rates", "calculator", "create_chart"),
        brief="Find HTA, pricing and reimbursement decisions in official sources: web_search checks HTA bodies and regulators "
              "first, and read_webpage opens a decision page for exact wording and dates. Use fda_approvals for US approval "
              "history and exchange_rates to compare prices across currencies.",
        domains=("ema.europa.eu", "iqwig.de", "g-ba.de", "has-sante.fr", "nice.org.uk", "aifa.gov.it", "aemps.gob.es",
                 "cda-amc.ca", "pbs.gov.au", "eunethta.eu"),
        starters=("Compare HTA outcomes for recent oncology launches in Germany, France and the UK",
                  "Which EU markets reimburse new medicines fastest, and why?",
                  "Summarize this year's EU pricing and reimbursement policy changes"),
    ),
    TemplateSpec(
        id="tpl_competitive", name="Competitive Intelligence", icon="🎯", category="Business",
        description="Signals on competitors' pipelines, launches, deals and positioning.",
        instructions="Act as a competitive intelligence analyst. For each competitor, cover what changed, when, and why it matters "
                     "for us. Separate confirmed facts from analyst opinion, cite company releases and filings first, and end with "
                     "three implications or recommended actions.",
        tools=("web_search", "read_webpage", "clinical_trials", "fda_approvals", "stock_prices", "search_space_files", "create_chart"),
        brief="Use clinical_trials for pipeline and trial questions (its sponsor, phase and start-date filters answer questions "
              "such as 'which phase 3 trials did X start this year'), fda_approvals for approvals, stock_prices with create_chart "
              "for how markets reacted, and web_search for news, deals and company releases. When a share price or a pipeline "
              "moved sharply, search for the reported reasons and cite them rather than guessing.",
        domains=("sec.gov", "fiercepharma.com", "fiercebiotech.com", "biopharmadive.com", "clinicaltrials.gov"),
        starters=("Which phase 3 trials did Novo Nordisk start this year?",
                  "Compare Eli Lilly's and Novo Nordisk's share prices over the last year",
                  "Which deals and partnerships did large pharma companies announce this quarter?"),
    ),
    TemplateSpec(
        id="tpl_regulatory", name="Regulatory Watch", icon="⚖️", category="Business",
        description="EMA, FDA and MHRA decisions and guidance, summarized for your team.",
        instructions="Summarize regulatory decisions and guidance precisely: agency, product or topic, decision, date, and what it "
                     "means in practice. Quote official wording for key conditions. Cite the agency's own pages first and say clearly "
                     "when a decision is pending or not yet published.",
        tools=("fda_approvals", "web_search", "read_webpage", "clinical_trials", "search_space_files"),
        brief="Use fda_approvals for FDA application and approval history. web_search checks EMA, MHRA, FDA and other "
              "regulators first; open the decision page with read_webpage to quote official wording. Distinguish novel "
              "approvals (new molecular entities and original biologics) from new indications, formulations and "
              "supplements, and label each one. Approval databases lag; never present a list as complete.",
        domains=("ema.europa.eu", "fda.gov", "gov.uk", "who.int", "pmda.go.jp", "canada.ca", "tga.gov.au"),
        starters=("Which new drugs did the FDA approve this month?",
                  "What did the EMA's CHMP recommend at its latest meeting?",
                  "Summarize new MHRA guidance published this quarter"),
    ),
    TemplateSpec(
        id="tpl_research", name="Research Assistant", icon="📚", category="Research",
        description="Deep, cited answers with academic rigor on any topic.",
        instructions="Provide detailed, well-sourced answers. Cite peer-reviewed papers and reputable institutions before blogs. "
                     "Start long answers with a short summary, structure them with clear headings, and state the strength and "
                     "limits of the evidence.",
        tools=("pubmed", "arxiv", "web_search", "read_webpage", "search_space_files"),
        brief="Use pubmed for biomedical and health evidence and arxiv for computer science, physics, mathematics and "
              "quantitative fields. Prefer systematic reviews, meta-analyses and recent studies; use web_search for "
              "institutions, guidelines and news.",
        domains=("nature.com", "thelancet.com", "nejm.org", "science.org", "cell.com", "who.int", "nih.gov"),
        starters=("Find the latest clinical evidence on GLP-1 drugs and heart failure",
                  "What does recent research say about AI in drug discovery?",
                  "Summarize recent papers on protein structure prediction"),
    ),
    TemplateSpec(
        id="tpl_data", name="Data Analyst", icon="📈", category="Research",
        description="Interpret statistics, spot trends and turn data into decisions.",
        instructions="Explain methodology and assumptions before conclusions. Use precise statistical language and define terms for "
                     "non-experts. Give confidence levels where possible, suggest the best chart for each finding, and highlight "
                     "actionable insights rather than observations.",
        tools=("stock_prices", "exchange_rates", "economic_data", "create_chart", "calculator", "web_search", "search_space_files"),
        brief="Work like a quantitative analyst. Fetch real series with stock_prices, exchange_rates or economic_data, then "
              "draw them with create_chart using the dataset ids those tools return. Report the key figures (latest value, "
              "change, high and low), the period and the data source, then what they mean.",
        domains=("data.worldbank.org", "oecd.org", "imf.org", "ec.europa.eu"),
        starters=("Chart Apple's stock price over the last 6 months",
                  "Compare GDP growth in Germany, France and Italy since 2015",
                  "How has the euro moved against the US dollar this year?"),
    ),
    TemplateSpec(
        id="tpl_patents", name="Patent Researcher", icon="🔬", category="Research",
        description="Search and summarize patents and prior art by topic or company.",
        instructions="For each patent give the number, title, filing and priority dates, assignee and status. Summarize the key "
                     "claims in plain language, compare them with related prior art, and note potential freedom-to-operate concerns "
                     "without giving legal advice.",
        tools=("web_search", "read_webpage", "pubmed", "search_space_files"),
        brief="web_search checks patent offices and patent databases first; open a patent page with read_webpage to read its "
              "claims, dates and assignee. Use pubmed for related scientific prior art.",
        domains=("patents.google.com", "lens.org", "epo.org", "wipo.int", "uspto.gov"),
        starters=("Find recent patents on mRNA delivery technologies",
                  "Who holds the key patents for oral GLP-1 formulations?",
                  "Summarize prior art for solid-state battery electrolytes"),
    ),
    TemplateSpec(
        id="tpl_study", name="Study Guide", icon="🎓", category="Learning",
        description="Turn notes, slides and textbooks into organized study guides.",
        instructions="Create study guides with clear headings, key definitions and short summaries. Add memory aids where helpful "
                     "and practice questions with answers at the end of each section. Explain complex ideas in simple language.",
        tools=("search_space_files", "web_search", "calculator"),
        brief="Work from the Space's files first with search_space_files; use web_search only to fill gaps.",
        starters=("Turn the key ideas of macroeconomics into a study guide",
                  "Give me ten practice questions on cell biology, with answers",
                  "Explain the Krebs cycle in simple terms"),
    ),
    TemplateSpec(
        id="tpl_tutor", name="Tutor", icon="🧠", category="Learning",
        description="Step-by-step help understanding a concept or solving a problem.",
        instructions="Act as a patient tutor. Break topics into small steps, ask a guiding question before giving answers, use "
                     "analogies and real examples, and check understanding before moving on.",
        tools=("calculator", "search_space_files", "web_search"),
        brief="Teach from your own knowledge; use calculator to check arithmetic and search_space_files for the learner's notes.",
        starters=("Help me understand compound interest step by step",
                  "Walk me through solving a quadratic equation",
                  "How do vaccines train the immune system?"),
    ),
    TemplateSpec(
        id="tpl_code", name="Code Helper", icon="💻", category="Development",
        description="Working code, clear explanations and focused debugging.",
        instructions="Give complete, working code using current best practices. Explain it step by step. When debugging, identify "
                     "the root cause before proposing a fix, include error handling, and mention complexity for algorithms.",
        tools=("web_search", "read_webpage", "search_space_files", "calculator"),
        brief="Answer from expertise; when versions, APIs or error messages matter, check official documentation with "
              "web_search and read_webpage.",
        domains=("docs.python.org", "developer.mozilla.org", "fastapi.tiangolo.com", "react.dev", "nextjs.org",
                 "stackoverflow.com"),
        starters=("How do I paginate a REST API in FastAPI?",
                  "Explain async and await in JavaScript with an example",
                  "What is the cleanest way to retry failed HTTP requests in Python?"),
    ),
    TemplateSpec(
        id="tpl_writing", name="Writing Coach", icon="📝", category="Personal",
        description="Constructive feedback, edits and fresh angles for your writing.",
        instructions="Give specific, constructive feedback rather than praise. Suggest concrete edits for clarity, tone and "
                     "structure, explain why each improves the text, and offer at least three angles when brainstorming.",
        tools=("search_space_files", "web_search"),
        brief="Work from the user's own text and the Space's files; search the web only for facts the writing depends on.",
        starters=("Make my executive summary more concise",
                  "Suggest three openings for a product launch email",
                  "How can I make a status update sound confident but not overpromising?"),
    ),
    TemplateSpec(
        id="tpl_trip", name="Trip Planner", icon="✈️", category="Personal",
        description="Itineraries, budgets and local recommendations for your trip.",
        instructions="Ask for budget, dates, interests and group size if they are missing. Plan day by day with morning, afternoon "
                     "and evening blocks, estimated costs and travel times, local favorites over tourist traps, and seasonal tips.",
        tools=("weather", "exchange_rates", "web_search", "read_webpage", "calculator"),
        brief="Use weather for forecasts, exchange_rates for budgets in the traveller's currency and web_search for opening "
              "hours, prices and events.",
        starters=("Plan a 5-day trip to Lisbon on a mid-range budget",
                  "What's the weather in Tokyo this week, and what should I pack?",
                  "How much is 1,000 US dollars in euros and yen today?"),
    ),
)
BY_ID = {template.id: template for template in TEMPLATES}
FEATURED = ("tpl_market_access", "tpl_competitive", "tpl_regulatory", "tpl_research", "tpl_data", "tpl_writing")
CATEGORIES = ("Business", "Research", "Learning", "Development", "Personal")


def get(template_id: str | None) -> TemplateSpec | None:
    return BY_ID.get(template_id or "")


def match(name: str, instructions: str) -> TemplateSpec | None:
    """The template an older Space was created from: unchanged instructions, or the template's own name."""
    instructions = (instructions or "").strip()
    return next((t for t in TEMPLATES if instructions and t.instructions == instructions), None) or \
        next((t for t in TEMPLATES if t.name.lower() == (name or "").strip().lower()), None)


def toolset(template_id: str | None, web_search: bool = True) -> tuple[str, ...]:
    """The tools a Space's agent may use. With web search off a Space answers only from its own files, through the
    file pipeline (retrieval, citations, and a plain "not in your files" when nothing matches), so it has no agent tools."""
    if not web_search:
        return ()
    template = get(template_id)
    return template.tools if template else GENERAL_TOOLS


def starters(template_id: str | None, space_name: str, has_files: bool) -> list[str]:
    """First questions for an empty Space: its template's own, or questions any Space answers well."""
    template = get(template_id)
    general = list(template.starters) if template else ["What's this Space for?", "What's new this week?",
                                                         f"Give me a briefing on {space_name}"]
    return ((["Summarize the key points across our files"] if has_files else []) + general)[:3]


def public(template: TemplateSpec) -> dict:
    """A template as the client sees it."""
    return {"id": template.id, "name": template.name, "description": template.description, "icon": template.icon,
            "category": template.category, "starters": list(template.starters),
            "tools": [{"id": tool, "label": TOOL_LABELS[tool]} for tool in template.tools]}
