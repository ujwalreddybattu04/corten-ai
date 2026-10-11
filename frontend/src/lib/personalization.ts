/**
 * Corten AI — Discover Personalization Engine  (v3 — production-grade)
 *
 * Industry-aligned client-side personalization inspired by:
 *   Netflix  — weighted category pools, aggressive re-ranking
 *   Spotify  — immediate feedback loop, interest-based boosting
 *   TikTok   — session-aware scoring, diversity injection
 *
 * Architecture:
 *   1. INTEREST BOOST   → selected interests get a +5 base affinity (cold-start fix)
 *   2. WEIGHTED FETCH   → fetch more articles from high-affinity categories
 *   3. SCORE + SORT     → single unified score (affinity + freshness + diversity)
 *   4. LIVE RE-RANK     → re-sort existing articles after every interaction
 *
 * Signal weights:
 *   click     +1.0   (weak implicit — user opened the article)
 *   like      +5.0   (strong explicit — "more of this")
 *   bookmark  +6.0   (strongest explicit — user saved it)
 *   dislike   -4.0   (strong negative — "less of this")
 *
 * Time decay: exponential with 7-day half-life
 *   weight(t) = e^(-λ * days_ago)  where λ = ln(2)/7 ≈ 0.099
 */

const STORAGE_KEY    = "discover_interactions_v2";
const AFFINITY_KEY   = "discover_affinities_v3"; // bumped to v3 for new weights
const DISLIKED_KEY   = "discover_disliked_v2";
const LIKED_KEY      = "discover_liked_v2";
const BOOKMARKED_KEY = "discover_bookmarked_v2";

const SIGNAL_WEIGHTS: Record<string, number> = {
    click:    1.0,
    like:     5.0,
    bookmark: 6.0,
    dislike:  -4.0,
};

// λ for 7-day half-life: ln(2)/7
const DECAY_LAMBDA = Math.LN2 / 7;

// Base affinity boost for user-selected interests (solves cold-start)
const INTEREST_BOOST = 5.0;

export interface Interaction {
    articleId: string;
    category:  string;
    action:    "click" | "like" | "bookmark" | "dislike";
    timestamp: number; // ms since epoch
}

export interface CategoryAffinities {
    [category: string]: number;
}

// ── Safe localStorage helpers ─────────────────────────────────────────────────

function lsGet(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
}
function lsSet(key: string, value: string): void {
    try { localStorage.setItem(key, value); } catch { /* ignore */ }
}
function lsRemove(key: string): void {
    try { localStorage.removeItem(key); } catch { /* ignore */ }
}

// ── Interaction store ─────────────────────────────────────────────────────────

function readInteractions(): Interaction[] {
    const raw = lsGet(STORAGE_KEY);
    if (!raw) return [];
    try { return JSON.parse(raw); } catch { return []; }
}

function writeInteractions(interactions: Interaction[]): void {
    // Keep only the last 500 interactions to cap localStorage usage
    lsSet(STORAGE_KEY, JSON.stringify(interactions.slice(-500)));
}

// ── ID set helpers (liked / bookmarked / disliked article IDs) ────────────────

function readIdSet(key: string): Set<string> {
    const raw = lsGet(key);
    if (!raw) return new Set();
    try { return new Set(JSON.parse(raw) as string[]); } catch { return new Set(); }
}

function writeIdSet(key: string, set: Set<string>): void {
    lsSet(key, JSON.stringify([...set]));
}

export function readDislikedIds():   Set<string> { return readIdSet(DISLIKED_KEY);   }
export function readLikedIds():      Set<string> { return readIdSet(LIKED_KEY);      }
export function readBookmarkedIds(): Set<string> { return readIdSet(BOOKMARKED_KEY); }

// ── Log a new interaction ────────────────────────────────────────────────────

export function logInteraction(
    articleId: string,
    category:  string,
    action:    Interaction["action"],
    isRemoving: boolean = false // true when user un-likes / un-bookmarks / un-dislikes
): void {
    if (typeof window === "undefined") return;

    const interactions = readInteractions();

    if (action === "click") {
        // Clicks are additive — each open counts (capped at 3 per article to avoid spam)
        const existingClicks = interactions.filter(
            i => i.articleId === articleId && i.action === "click"
        ).length;
        if (existingClicks < 3) {
            interactions.push({ articleId, category, action, timestamp: Date.now() });
            writeInteractions(interactions);
        }
    } else {
        // Explicit signals: toggle (add on first, remove on second)
        const idx = interactions.findIndex(
            i => i.articleId === articleId && i.action === action
        );
        if (isRemoving || idx !== -1) {
            if (idx !== -1) interactions.splice(idx, 1);
        } else {
            interactions.push({ articleId, category, action, timestamp: Date.now() });
        }
        writeInteractions(interactions);
    }

    // Update per-action ID sets for fast UI restoration
    if (action === "like") {
        const set = readLikedIds();
        isRemoving ? set.delete(articleId) : set.add(articleId);
        writeIdSet(LIKED_KEY, set);
    } else if (action === "bookmark") {
        const set = readBookmarkedIds();
        isRemoving ? set.delete(articleId) : set.add(articleId);
        writeIdSet(BOOKMARKED_KEY, set);
    } else if (action === "dislike") {
        const set = readDislikedIds();
        isRemoving ? set.delete(articleId) : set.add(articleId);
        writeIdSet(DISLIKED_KEY, set);
    }

    // Invalidate cached affinities so next call to computeAffinities is fresh
    lsRemove(AFFINITY_KEY);
}

// ── Read saved user interests ────────────────────────────────────────────────

function readSavedInterests(): string[] {
    const raw = lsGet("discover_interests");
    if (!raw) return [];
    try { return JSON.parse(raw) as string[]; } catch { return []; }
}

// ── Compute affinity scores from interaction history + interests ─────────────
//
// This is the core of the engine.
// 1. Start with a base boost for user-selected interests (+5 each)
// 2. Accumulate signal weights with time decay for every interaction
// 3. Clamp to [-15, 25] to prevent runaway values
//
// The result is a map from category → score that can be:
//   positive = user likes this category
//   negative = user dislikes this category
//   zero     = no opinion / neutral

export function computeAffinities(): CategoryAffinities {
    if (typeof window === "undefined") return {};

    // Return cached affinities if fresh (< 15 seconds old)
    // Short cache = faster feedback after interactions
    const cached = lsGet(AFFINITY_KEY);
    if (cached) {
        try {
            const { affinities, computedAt } = JSON.parse(cached);
            if (Date.now() - computedAt < 15_000) return affinities;
        } catch { /* recompute */ }
    }

    const affinities: CategoryAffinities = {};

    // Step 1: Boost selected interests (cold-start fix)
    const interests = readSavedInterests();
    for (const cat of interests) {
        affinities[cat] = (affinities[cat] ?? 0) + INTEREST_BOOST;
    }

    // Step 2: Accumulate interaction signals with time decay
    const interactions = readInteractions();
    const nowMs = Date.now();

    for (const i of interactions) {
        const daysAgo     = (nowMs - i.timestamp) / 86_400_000;
        const decayWeight = Math.exp(-DECAY_LAMBDA * daysAgo);
        const weight      = (SIGNAL_WEIGHTS[i.action] ?? 0) * decayWeight;
        affinities[i.category] = (affinities[i.category] ?? 0) + weight;
    }

    // Step 3: Clamp scores
    for (const cat in affinities) {
        affinities[cat] = Math.max(-15, Math.min(25, affinities[cat]));
    }

    lsSet(AFFINITY_KEY, JSON.stringify({ affinities, computedAt: Date.now() }));
    return affinities;
}

// ── Compute weighted fetch sizes per category ────────────────────────────────
//
// Industry approach: fetch MORE articles from high-affinity categories.
// This ensures the raw pool is already biased toward content the user loves.
//
// Returns { category: pageSize } map.

export function getWeightedFetchSizes(
    categories: string[],
    affinities: CategoryAffinities,
    totalBudget: number = 50 // total articles to fetch across all categories
): Record<string, number> {
    const MIN_PER_CAT = 3;  // never drop below 3 (diversity floor)
    const MAX_PER_CAT = 18; // never exceed 18 (API page size cap)

    // Calculate raw weights: softmax-like transformation of affinities
    // Shift affinities so the minimum is 1 (all positive for ratio calculation)
    const scores = categories.map(cat => affinities[cat] ?? 0);
    const minScore = Math.min(...scores, 0);
    const shifted = scores.map(s => s - minScore + 1); // guarantee > 0
    const totalWeight = shifted.reduce((a, b) => a + b, 0);

    const result: Record<string, number> = {};
    let allocated = 0;

    for (let i = 0; i < categories.length; i++) {
        const ratio = shifted[i] / totalWeight;
        const raw = Math.round(ratio * totalBudget);
        const clamped = Math.max(MIN_PER_CAT, Math.min(MAX_PER_CAT, raw));
        result[categories[i]] = clamped;
        allocated += clamped;
    }

    // If we over-allocated, trim from lowest-affinity categories
    if (allocated > totalBudget + 10) {
        const sorted = [...categories].sort(
            (a, b) => (affinities[a] ?? 0) - (affinities[b] ?? 0)
        );
        for (const cat of sorted) {
            if (allocated <= totalBudget) break;
            const reduce = Math.min(result[cat] - MIN_PER_CAT, allocated - totalBudget);
            result[cat] -= reduce;
            allocated -= reduce;
        }
    }

    return result;
}

// ── Score a single article ────────────────────────────────────────────────────
//
// Unified score = category affinity + freshness bonus
// Higher score → higher position in feed

export function scoreArticle(
    article: { category?: string; publishedAt?: string },
    affinities: CategoryAffinities
): number {
    const affinityScore = affinities[article.category ?? ""] ?? 0;

    // Freshness bonus: < 3 h → +3, < 6 h → +2, < 24 h → +1
    let freshnessBonus = 0;
    if (article.publishedAt) {
        const hoursOld = (Date.now() - new Date(article.publishedAt).getTime()) / 3_600_000;
        if (!isNaN(hoursOld)) {
            if (hoursOld < 3)       freshnessBonus = 3;
            else if (hoursOld < 6)  freshnessBonus = 2;
            else if (hoursOld < 24) freshnessBonus = 1;
        }
    }

    return affinityScore + freshnessBonus;
}

// ── Rank and mix articles (v3 — sort + diversity injection) ──────────────────
//
// New approach (replaces the complex bucket interleaving):
//   1. Score every article with unified scoring
//   2. Sort by score descending (highest affinity + freshest → top)
//   3. Inject diversity: ensure no more than 3 consecutive articles from
//      the same category (prevents monotonous feed)
//   4. Filter out individually disliked articles
//
// This is simpler, more predictable, and produces visibly different results
// after even a single interaction.

export function rankArticles<T extends { id: string; category?: string; publishedAt?: string }>(
    articles: T[],
    affinities: CategoryAffinities,
    dislikedArticleIds: Set<string>
): T[] {
    if (typeof window === "undefined") return articles;
    if (!articles.length) return articles;

    // Filter out individually disliked articles
    const filtered = articles.filter(a => !dislikedArticleIds.has(a.id));
    if (!filtered.length) return filtered;

    // Score every article
    const scored = filtered.map(a => ({
        article: a,
        score: scoreArticle(a, affinities),
    }));

    // Sort by score descending (primary), then by publishedAt descending (secondary)
    scored.sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        // Tiebreak: newer articles first
        const timeA = a.article.publishedAt ? new Date(a.article.publishedAt).getTime() : 0;
        const timeB = b.article.publishedAt ? new Date(b.article.publishedAt).getTime() : 0;
        return timeB - timeA;
    });

    // Diversity injection: prevent more than 3 consecutive same-category articles
    const result: T[] = [];
    const deferred: typeof scored = [];

    for (const item of scored) {
        const cat = item.article.category ?? "";
        // Count how many of the last 3 placed articles share this category
        const recentSame = result.slice(-3).filter(r => (r.category ?? "") === cat).length;

        if (recentSame >= 3) {
            // Too many in a row from this category — defer it
            deferred.push(item);
        } else {
            result.push(item.article);
        }
    }

    // Append deferred articles at the end (still in score order)
    for (const item of deferred) {
        result.push(item.article);
    }

    return result;
}

// ── Live re-rank (for instant feedback after interactions) ────────────────────
//
// Called after like/dislike/bookmark to immediately re-sort the visible feed.
// This is what makes personalization feel "alive" — the user sees the effect
// of their interaction right away without waiting for a re-fetch.

export function liveReRank<T extends { id: string; category?: string; publishedAt?: string }>(
    currentArticles: T[]
): T[] {
    const affinities = computeAffinities();
    const disliked = readDislikedIds();
    return rankArticles(currentArticles, affinities, disliked);
}

// ── Public helpers ────────────────────────────────────────────────────────────

export function getTopCategories(affinities: CategoryAffinities): {
    liked: string[];
    disliked: string[];
} {
    const entries = Object.entries(affinities);
    return {
        liked:    entries.filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([c]) => c),
        disliked: entries.filter(([, s]) => s < 0).sort((a, b) => a[1] - b[1]).slice(0, 3).map(([c]) => c),
    };
}
