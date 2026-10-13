/** Ready-made Spaces, as cards. The server owns each template's instructions, agent tools and first questions
 *  (GET /api/v1/spaces/templates); this list only lets the cards render instantly and is checked against it in tests. */
export interface TemplateCard {
    id: string;
    name: string;
    description: string;
    icon: string;
    category: TemplateCategory;
}

export const TEMPLATE_CATEGORIES = ["Business", "Research", "Learning", "Development", "Personal"] as const;
export type TemplateCategory = typeof TEMPLATE_CATEGORIES[number];

export const SPACE_TEMPLATES: TemplateCard[] = [
    { id: "tpl_market_access", name: "Market Access & Pricing", icon: "💊", category: "Business",
      description: "Track HTA decisions, pricing and reimbursement across markets." },
    { id: "tpl_competitive", name: "Competitive Intelligence", icon: "🎯", category: "Business",
      description: "Signals on competitors' pipelines, launches, deals and positioning." },
    { id: "tpl_regulatory", name: "Regulatory Watch", icon: "⚖️", category: "Business",
      description: "EMA, FDA and MHRA decisions and guidance, summarized for your team." },
    { id: "tpl_research", name: "Research Assistant", icon: "📚", category: "Research",
      description: "Deep, cited answers with academic rigor on any topic." },
    { id: "tpl_data", name: "Data Analyst", icon: "📈", category: "Research",
      description: "Interpret statistics, spot trends and turn data into decisions." },
    { id: "tpl_patents", name: "Patent Researcher", icon: "🔬", category: "Research",
      description: "Search and summarize patents and prior art by topic or company." },
    { id: "tpl_study", name: "Study Guide", icon: "🎓", category: "Learning",
      description: "Turn notes, slides and textbooks into organized study guides." },
    { id: "tpl_tutor", name: "Tutor", icon: "🧠", category: "Learning",
      description: "Step-by-step help understanding a concept or solving a problem." },
    { id: "tpl_code", name: "Code Helper", icon: "💻", category: "Development",
      description: "Working code, clear explanations and focused debugging." },
    { id: "tpl_writing", name: "Writing Coach", icon: "📝", category: "Personal",
      description: "Constructive feedback, edits and fresh angles for your writing." },
    { id: "tpl_trip", name: "Trip Planner", icon: "✈️", category: "Personal",
      description: "Itineraries, budgets and local recommendations for your trip." },
];

const FILES_STARTER = "Summarize the key points across our files";

/** First questions to suggest in an empty Space: its agent's (from the server), otherwise questions every Space
 *  answers well (its overview, news on its topic). Files uploaded since the Space loaded put a files question first. */
export function starterQuestions(space: { name: string; agent?: { starters?: string[] } }, hasFiles: boolean): string[] {
    const fromAgent = (space.agent?.starters ?? []).filter(item => typeof item === "string" && item.trim() && item !== FILES_STARTER);
    const general = fromAgent.length ? fromAgent : ["What's this Space for?", "What's new this week?", `Give me a briefing on ${space.name}`];
    return [...(hasFiles ? [FILES_STARTER] : []), ...general].slice(0, 3);
}

/** Templates shown on the Spaces home page. */
export const FEATURED_TEMPLATES = ["tpl_market_access", "tpl_competitive", "tpl_regulatory", "tpl_research", "tpl_data", "tpl_writing"]
    .map(id => SPACE_TEMPLATES.find(template => template.id === id)!);
