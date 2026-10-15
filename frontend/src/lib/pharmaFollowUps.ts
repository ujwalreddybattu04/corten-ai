import type { PharmaRecord, PharmaTurn } from "./pharmaRecord";

type Topic = "documents" | "label" | "trials" | "results" | "endpoints" | "dates" | "literature" | "timeline" | "forecast" | "recall" | "source";
type Candidate = { question: string; topic: Topic };

export function pharmaQuestionKey(question: string): string {
    return question.normalize("NFKC").toLocaleLowerCase("en").replace(/[\u200B-\u200D\uFEFF]/g, "")
        .match(/[\p{L}\p{N}]+/gu)?.join(" ") || "";
}

/** Intent matching keeps paraphrases of an answered question out of Related too. */
function topics(question: string): Set<Topic> {
    const text = pharmaQuestionKey(question), found = new Set<Topic>();
    if (/\b(?:assessment|procedure|approval letter|regulatory documents?|decision documents?)\b/.test(text)) found.add("documents");
    if (/\b(?:label|labeling|labelling|prescribing information|product information|safety|warnings?)\b/.test(text)) found.add("label");
    if (/\b(?:results?|outcomes?|efficacy numbers?|readouts?)\b/.test(text)) found.add("results");
    if (/\b(?:endpoints?|study design|trial design|populations?|eligibility)\b/.test(text)) found.add("endpoints");
    if (/\b(?:dates?|milestones?|completion|estimated|actual)\b/.test(text)) found.add("dates");
    if (/\b(?:trials?|studies)\b/.test(text) && !found.has("results") && !found.has("endpoints") && !found.has("dates")) found.add("trials");
    if (/\b(?:publications?|published|literature|papers?|scientific evidence|clinical evidence)\b/.test(text)) found.add("literature");
    if (/\b(?:timeline|history|historical)\b/.test(text)) found.add("timeline");
    if (/\b(?:forecast|forecasting|assumptions?|commercial implications?)\b/.test(text)) found.add("forecast");
    if (/\b(?:recalls?|affected lots?|batch(?:es)?)\b/.test(text)) found.add("recall");
    if (/\b(?:primary announcement|original announcement|original evidence|primary source)\b/.test(text)) found.add("source");
    return found;
}

function nearDuplicate(a: string, b: string): boolean {
    if (a === b) return true;
    const filler = new Set(["a", "an", "the", "what", "which", "are", "is", "does", "do", "for", "of", "in", "to", "can", "you", "please", "find", "show", "retrieve", "check"]);
    const left = new Set(a.split(" ").filter(word => !filler.has(word))), right = new Set(b.split(" ").filter(word => !filler.has(word)));
    const intersection = [...left].filter(word => right.has(word)).length;
    return intersection >= 3 && intersection / new Set([...left, ...right]).size >= .72;
}

/** Suggestions are derived, never randomized or billed as another model call. */
export function pharmaFollowUps(record: PharmaRecord, turns: PharmaTurn[]): string[] {
    const { item } = record, details = item.details || {}, candidates: Candidate[] = [];
    const name = (value: string | undefined) => value?.replace(/[\r\n]+/g, " ").trim().slice(0, 90) || "";
    const ingredient = name(details.ingredients?.[0] || item.drugs?.[0]?.name || details.interventions?.[0]);
    const product = item.source === "ema" || item.source === "fda" ? name(item.title.split(/\s[·•]\s/)[0]) : ingredient;
    const subject = ingredient || product;
    const add = (topic: Topic, question: string) => candidates.push({ topic, question });
    if (item.source === "ema" && product) {
        add("documents", `Find EMA assessment documents for ${product}${details.latest_procedure ? `, procedure ${name(details.latest_procedure)}` : ""}.`);
        add("label", `Find current EMA product information for ${product}.`);
    } else if (item.source === "fda" && subject) {
        add("documents", `Find FDA action documents for ${name(details.application) || subject}.`);
        add("label", `Find current FDA labeling for ${subject}.`);
    } else if (item.source === "trials" && details.study_id) {
        const study = name(details.study_id);
        add("results", details.results_posted ? `Review the posted primary results for ${study}.` : `Check whether results have been posted for ${study}.`);
        add("endpoints", `What primary endpoints and population are registered for ${study}?`);
        add("dates", `Separate actual and estimated milestones for ${study}.`);
    } else if (item.source === "fda_safety") {
        if (subject) add("recall", `Find the FDA recall notice and affected lots for ${subject}.`);
        else add("source", "Find the original FDA safety notice behind this record.");
    } else {
        add("source", "Find the primary announcement supporting this report.");
    }
    if (subject) {
        add("trials", `Find registered clinical trials for ${subject}.`);
        add("literature", `Find published clinical evidence for ${subject}.`);
        add("timeline", `Show the verified regulatory timeline for ${subject}.`);
    }
    if (item.impact?.rating === "Material") add("forecast", "Which evidence-based forecast assumptions should be reviewed after this event?");

    // The first turn is the automatic brief, not a user-selected research task.
    const asked = turns.slice(1).map(turn => pharmaQuestionKey(turn.query));
    const covered = new Set(turns.slice(1).flatMap(turn => [...topics(turn.query)]));
    const answer = turns.at(-1)?.answer || "";
    const latest = turns.length > 1 ? topics(turns.at(-1)!.query) : new Set<Topic>();
    const next: Partial<Record<Topic, Topic[]>> = {
        documents: ["label", "timeline", "trials", "literature"], label: ["literature", "trials", "documents", "timeline"],
        trials: ["results", "endpoints", "literature", "dates", "label"], results: ["endpoints", "dates", "literature"],
        endpoints: ["results", "dates", "literature"], dates: ["results", "endpoints", "literature"],
        literature: ["trials", "label", "documents"], timeline: ["documents", "label", "trials"],
    };
    const priorities = [...new Set([...latest].flatMap(topic => next[topic] || []))];
    if (priorities.length) {
        const rank = (topic: Topic) => priorities.includes(topic) ? priorities.indexOf(topic) : priorities.length;
        candidates.sort((a, b) => rank(a.topic) - rank(b.topic));
    } else if (/not (?:established|detailed|disclosed)|unresolved|missing|does not (?:identify|describe|establish)/i.test(answer)) {
        candidates.sort((a, b) => Number(["documents", "source", "results"].includes(b.topic)) - Number(["documents", "source", "results"].includes(a.topic)));
    }
    const seen = new Set<string>();
    return candidates.filter(candidate => {
        const key = pharmaQuestionKey(candidate.question);
        if (covered.has(candidate.topic) || seen.has(key) || asked.some(previous => nearDuplicate(previous, key))) return false;
        seen.add(key); return true;
    }).slice(0, 3).map(candidate => candidate.question);
}
