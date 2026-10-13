/** Ready-made Spaces: a name, description and answer instructions to start from. */
export interface SpaceTemplate {
    id: string;
    name: string;
    description: string;
    icon: string;
    category: TemplateCategory;
    instructions: string;
}

export const TEMPLATE_CATEGORIES = ["Business", "Research", "Learning", "Development", "Personal"] as const;
export type TemplateCategory = typeof TEMPLATE_CATEGORIES[number];

export const SPACE_TEMPLATES: SpaceTemplate[] = [
    {
        id: "tpl_market_access", name: "Market Access & Pricing", icon: "💊", category: "Business",
        description: "Track HTA decisions, pricing and reimbursement across markets.",
        instructions: "You are a senior market access analyst. Lead with the answer, then the evidence. Compare countries in tables "
            + "(HTA body, decision, date, price or discount, conditions). Prefer regulator, HTA and payer sources, give dates for "
            + "every decision, and flag where evidence is missing or outdated.",
    },
    {
        id: "tpl_competitive", name: "Competitive Intelligence", icon: "🎯", category: "Business",
        description: "Signals on competitors' pipelines, launches, deals and positioning.",
        instructions: "Act as a competitive intelligence analyst. For each competitor, cover what changed, when, and why it matters "
            + "for us. Separate confirmed facts from analyst opinion, cite company releases and filings first, and end with "
            + "three implications or recommended actions.",
    },
    {
        id: "tpl_regulatory", name: "Regulatory Watch", icon: "⚖️", category: "Business",
        description: "EMA, FDA and MHRA decisions and guidance, summarized for your team.",
        instructions: "Summarize regulatory decisions and guidance precisely: agency, product or topic, decision, date, and what it "
            + "means in practice. Quote official wording for key conditions. Cite the agency's own pages first and say clearly "
            + "when a decision is pending or not yet published.",
    },
    {
        id: "tpl_research", name: "Research Assistant", icon: "📚", category: "Research",
        description: "Deep, cited answers with academic rigor on any topic.",
        instructions: "Provide detailed, well-sourced answers. Cite peer-reviewed papers and reputable institutions before blogs. "
            + "Start long answers with a short summary, structure them with clear headings, and state the strength and "
            + "limits of the evidence.",
    },
    {
        id: "tpl_data", name: "Data Analyst", icon: "📈", category: "Research",
        description: "Interpret statistics, spot trends and turn data into decisions.",
        instructions: "Explain methodology and assumptions before conclusions. Use precise statistical language and define terms for "
            + "non-experts. Give confidence levels where possible, suggest the best chart for each finding, and highlight "
            + "actionable insights rather than observations.",
    },
    {
        id: "tpl_patents", name: "Patent Researcher", icon: "🔬", category: "Research",
        description: "Search and summarize patents and prior art by topic or company.",
        instructions: "For each patent give the number, title, filing and priority dates, assignee and status. Summarize the key "
            + "claims in plain language, compare them with related prior art, and note potential freedom-to-operate concerns "
            + "without giving legal advice.",
    },
    {
        id: "tpl_study", name: "Study Guide", icon: "🎓", category: "Learning",
        description: "Turn notes, slides and textbooks into organized study guides.",
        instructions: "Create study guides with clear headings, key definitions and short summaries. Add memory aids where helpful "
            + "and practice questions with answers at the end of each section. Explain complex ideas in simple language.",
    },
    {
        id: "tpl_tutor", name: "Tutor", icon: "🧠", category: "Learning",
        description: "Step-by-step help understanding a concept or solving a problem.",
        instructions: "Act as a patient tutor. Break topics into small steps, ask a guiding question before giving answers, use "
            + "analogies and real examples, and check understanding before moving on.",
    },
    {
        id: "tpl_code", name: "Code Helper", icon: "💻", category: "Development",
        description: "Working code, clear explanations and focused debugging.",
        instructions: "Give complete, working code using current best practices. Explain it step by step. When debugging, identify "
            + "the root cause before proposing a fix, include error handling, and mention complexity for algorithms.",
    },
    {
        id: "tpl_writing", name: "Writing Coach", icon: "📝", category: "Personal",
        description: "Constructive feedback, edits and fresh angles for your writing.",
        instructions: "Give specific, constructive feedback rather than praise. Suggest concrete edits for clarity, tone and "
            + "structure, explain why each improves the text, and offer at least three angles when brainstorming.",
    },
    {
        id: "tpl_trip", name: "Trip Planner", icon: "✈️", category: "Personal",
        description: "Itineraries, budgets and local recommendations for your trip.",
        instructions: "Ask for budget, dates, interests and group size if they are missing. Plan day by day with morning, afternoon "
            + "and evening blocks, estimated costs and travel times, local favorites over tourist traps, and seasonal tips.",
    },
];

/** Expert first questions for Spaces started from a template. */
const STARTERS: Record<string, string[]> = {
    tpl_market_access: [
        "Compare HTA outcomes for recent oncology launches in Germany, France and the UK",
        "Which EU markets reimburse new medicines fastest, and why?",
        "Summarize this year's EU pricing and reimbursement policy changes",
    ],
    tpl_competitive: [
        "What changed in our main competitors' pipelines this month?",
        "Which deals and partnerships did competitors announce this quarter?",
        "Compare the late-stage oncology pipelines of the top five companies",
    ],
    tpl_regulatory: [
        "What did the EMA's CHMP recommend at its latest meeting?",
        "Which FDA approvals this month matter most for oncology?",
        "Summarize new MHRA guidance published this quarter",
    ],
    tpl_research: [
        "What does recent research say about AI in drug discovery?",
        "Compare the leading explanations for long COVID",
        "Which 2026 papers on CAR-T therapy are most cited?",
    ],
    tpl_data: [
        "How should I compare growth rates across markets of different sizes?",
        "Which chart best shows market share changing over time?",
        "How do I check a sales forecast for seasonality?",
    ],
    tpl_patents: [
        "Find recent patents on mRNA delivery technologies",
        "Who holds the key patents for oral GLP-1 formulations?",
        "Summarize prior art for solid-state battery electrolytes",
    ],
    tpl_study: [
        "Turn the key ideas of macroeconomics into a study guide",
        "Give me ten practice questions on cell biology, with answers",
        "Explain the Krebs cycle in simple terms",
    ],
    tpl_tutor: [
        "Help me understand compound interest step by step",
        "Walk me through solving a quadratic equation",
        "How do vaccines train the immune system?",
    ],
    tpl_code: [
        "How do I paginate a REST API in FastAPI?",
        "Explain async and await in JavaScript with an example",
        "What is the cleanest way to retry failed HTTP requests in Python?",
    ],
    tpl_writing: [
        "Make my executive summary more concise",
        "Suggest three openings for a product launch email",
        "How can I make a status update sound confident but not overpromising?",
    ],
    tpl_trip: [
        "Plan a 5-day trip to Lisbon on a mid-range budget",
        "When is the best time to visit Japan with fewer crowds?",
        "Plan a family-friendly weekend in Barcelona",
    ],
};

/** First questions to suggest in an empty Space: the template's own when the Space came from one,
 *  otherwise questions every Space can answer well (its overview, news on its topic, its files). */
export function starterQuestions(space: { name: string; instructions: string }, hasFiles: boolean): string[] {
    const template = SPACE_TEMPLATES.find(item => item.instructions === space.instructions)
        ?? SPACE_TEMPLATES.find(item => item.name.toLowerCase() === space.name.trim().toLowerCase());
    const general = template ? STARTERS[template.id] ?? [] : ["What's this Space for?", "What's new this week?", `Give me a briefing on ${space.name}`];
    return [...(hasFiles ? ["Summarize the key points across our files"] : []), ...general].slice(0, 3);
}

/** Templates shown on the Spaces home page. */
export const FEATURED_TEMPLATES = ["tpl_market_access", "tpl_competitive", "tpl_regulatory", "tpl_research", "tpl_data", "tpl_writing"]
    .map(id => SPACE_TEMPLATES.find(template => template.id === id)!);
