"""Keyword intent classification and topic-cluster / pillar planning."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

STOP = {"a", "an", "the", "to", "for", "of", "in", "on", "and", "or", "my", "is", "do", "i", "with", "under"}
# words that signal intent, so they must never become a topic name
MODIFIERS = {
    "how", "what", "why", "when", "best", "top", "rated", "buy", "price", "cheap", "review", "vs",
    "alternatives", "guide", "beginners", "tips", "clean", "use", "order", "online", "sale", "discount",
    "code", "working", "not", "login", "sign", "official", "site", "customer", "service", "drip", "brewer",
    "maker", "200",
}

NAVIGATIONAL = ("login", "log in", "sign in", "official site", "customer service", "contact")
TRANSACTIONAL = ("buy", "price", "pricing", "cheap", "deal", "discount", "coupon", "order ", "for sale", "shop", "near me")
COMMERCIAL = ("best", "top ", "review", "reviews", " vs ", "versus", "alternative", "compare", "comparison", "worth it")
INFORMATIONAL = ("how", "what", "why", "when", "guide", "tutorial", "tips", "ideas", "examples", "difference", "not working")


def classify_intent(keyword: str, brand_terms: tuple[str, ...] = ("bean atlas",)) -> str:
    k = f" {keyword.lower().strip()} "
    if any(b in k for b in brand_terms) or any(n in k for n in NAVIGATIONAL):
        return "navigational"
    if any(t in k for t in TRANSACTIONAL):
        return "transactional"
    if any(c in k for c in COMMERCIAL):
        return "commercial"
    return "informational"


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


@dataclass
class Keyword:
    keyword: str
    volume: int
    difficulty: int
    intent: str = ""
    theme: str = ""

    @property
    def opportunity(self) -> float:
        """Volume discounted by difficulty; a relative score, not a traffic forecast."""
        return round(self.volume / (self.difficulty + 10), 1)


@dataclass
class Cluster:
    theme: str
    intent: str
    keywords: list[Keyword] = field(default_factory=list)

    @property
    def primary(self) -> Keyword:
        return max(self.keywords, key=lambda k: (k.volume, k.keyword))

    @property
    def volume(self) -> int:
        return sum(k.volume for k in self.keywords)

    @property
    def avg_difficulty(self) -> float:
        return round(sum(k.difficulty for k in self.keywords) / len(self.keywords), 1)

    @property
    def opportunity(self) -> float:
        return round(self.volume / (self.avg_difficulty + 10), 1)


def load_keywords(path: str) -> list[Keyword]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return [Keyword(r["keyword"].strip().lower(), int(r["volume"]), int(r["difficulty"])) for r in rows]


def _theme_label(token: str, members: list[Keyword]) -> str:
    """Name a theme by the commonest adjacent word pair containing its token
    ('cold brew' rather than 'cold'); falls back to the bare token."""
    pairs: Counter = Counter()
    for k in members:
        t = tokens(k.keyword)
        for a, b in zip(t, t[1:]):
            if token in (a, b) and not ({a, b} & MODIFIERS):
                pairs[f"{a} {b}"] += 1
    if pairs:
        pair, n = pairs.most_common(1)[0]
        if n >= 0.6 * len(members):
            return pair
    return token


def assign_themes(kws: list[Keyword], min_size: int = 4) -> None:
    """Greedy theme discovery: repeatedly pick the most common non-modifier token."""
    remaining = [k for k in kws if k.intent != "navigational"]
    for k in kws:
        if k.intent == "navigational":
            k.theme = "brand"
    while remaining:
        counts: Counter = Counter()
        vol: Counter = Counter()
        for k in remaining:
            for t in set(tokens(k.keyword)) - MODIFIERS:
                counts[t] += 1
                vol[t] += k.volume
        if not counts:
            break
        # most frequent; ties -> more volume -> longer (more specific) token -> alpha
        best, n = max(counts.items(), key=lambda kv: (kv[1], vol[kv[0]], len(kv[0]), kv[0]))
        if n < min_size:
            break
        members = [x for x in remaining if best in tokens(x.keyword)]
        label = _theme_label(best, members)
        for k in members:
            k.theme = label
            remaining.remove(k)
    for k in remaining:
        k.theme = "misc"


def build_clusters(kws: list[Keyword]) -> list[Cluster]:
    for k in kws:
        k.intent = classify_intent(k.keyword)
    assign_themes(kws)
    groups: dict[tuple[str, str], list[Keyword]] = defaultdict(list)
    for k in kws:
        groups[(k.theme, k.intent)].append(k)
    return sorted((Cluster(t, i, v) for (t, i), v in groups.items()), key=lambda c: -c.opportunity)


@dataclass
class Pillar:
    theme: str
    keyword: str
    clusters: list[Cluster]

    @property
    def volume(self) -> int:
        return sum(c.volume for c in self.clusters)


def plan_pillars(clusters: list[Cluster]) -> list[Pillar]:
    """One pillar per theme. Pillar keyword = highest-volume non-navigational,
    short (<=3 token) keyword; supporting pages = the remaining clusters."""
    by_theme: dict[str, list[Cluster]] = defaultdict(list)
    for c in clusters:
        if c.theme != "brand":  # navigational brand terms are support content, not a pillar
            by_theme[c.theme].append(c)
    pillars = []
    for theme, cs in by_theme.items():
        cands = [k for c in cs if c.intent != "navigational" for k in c.keywords if len(k.keyword.split()) <= 3]
        pk = max(cands or [k for c in cs for k in c.keywords], key=lambda k: (k.volume, k.keyword))
        pillars.append(Pillar(theme, pk.keyword, sorted(cs, key=lambda c: -c.opportunity)))
    return sorted(pillars, key=lambda p: -p.volume)


def clusters_to_rows(clusters: list[Cluster]) -> list[dict]:
    return [{
        "theme": c.theme, "intent": c.intent, "primary_keyword": c.primary.keyword,
        "keywords": len(c.keywords), "total_volume": c.volume,
        "avg_difficulty": c.avg_difficulty, "opportunity": c.opportunity,
    } for c in clusters]
