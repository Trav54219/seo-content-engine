"""Content-brief generator. Rule-based templates; no LLM, no live SERP data."""
from __future__ import annotations

from .keywords import Cluster, Pillar

OUTLINES = {
    "informational": ["What it is and who it is for", "Step-by-step walkthrough", "Common mistakes and fixes",
                      "Tools and equipment you actually need", "FAQ"],
    "commercial": ["How we evaluated (criteria and method)", "Comparison table", "Picks by use case",
                   "Who should skip this", "FAQ"],
    "transactional": ["Offer summary above the fold", "Pricing and what is included", "Trust signals (returns, shipping, support)",
                      "Comparison with alternatives", "FAQ and clear call to action"],
    "navigational": ["Direct answer and link to the destination", "Support and contact options"],
}
SCHEMA = {"informational": "Article + FAQPage (HowTo only when steps are real)", "commercial": "Article + ItemList (Review where applicable)",
          "transactional": "Product + Offer", "navigational": "Organization / WebSite"}
BASE_WORDS = {"informational": 1400, "commercial": 1800, "transactional": 600, "navigational": 250}


def target_words(intent: str, avg_difficulty: float) -> int:
    """Harder keywords need more depth; capped so briefs stay plausible."""
    extra = max(0, avg_difficulty - 40) * 15
    return int(round((BASE_WORDS[intent] + extra) / 50) * 50)


def slugify(s: str) -> str:
    return "-".join("".join(ch if ch.isalnum() else " " for ch in s.lower()).split())


def meta_title(primary: str, intent: str) -> str:
    suffix = {"informational": " (Practical Guide)", "commercial": " (Tested and Compared)",
              "transactional": " | Bean Atlas", "navigational": ""}[intent]
    t = primary.title() + suffix
    return t if len(t) <= 60 else t[:57].rstrip() + "..."


def meta_description(primary: str, intent: str) -> str:
    d = {"informational": f"Clear answers on {primary}: steps, common mistakes and what to buy only if you need it.",
         "commercial": f"{primary.capitalize()} compared on the criteria that matter, with picks by budget and use case.",
         "transactional": f"{primary.capitalize()}: current options, what is included and how returns and support work.",
         "navigational": f"Find {primary} and get help quickly."}[intent]
    return d if len(d) <= 155 else d[:152].rstrip() + "..."


def make_brief(cluster: Cluster, pillar: Pillar) -> dict:
    primary = cluster.primary
    secondary = [k.keyword for k in sorted(cluster.keywords, key=lambda k: -k.volume) if k is not primary][:6]
    return {
        "slug": slugify(primary.keyword),
        "primary_keyword": primary.keyword,
        "secondary_keywords": secondary,
        "intent": cluster.intent,
        "theme": cluster.theme,
        "pillar_keyword": pillar.keyword,
        "is_pillar": primary.keyword == pillar.keyword,
        "total_volume": cluster.volume,
        "avg_difficulty": cluster.avg_difficulty,
        "target_words": target_words(cluster.intent, cluster.avg_difficulty),
        "meta_title": meta_title(primary.keyword, cluster.intent),
        "meta_description": meta_description(primary.keyword, cluster.intent),
        "outline": OUTLINES[cluster.intent],
        "schema": SCHEMA[cluster.intent],
        "internal_links": {"up": pillar.keyword if primary.keyword != pillar.keyword else None,
                           "across": [c.primary.keyword for c in pillar.clusters if c is not cluster][:3]},
    }


def brief_to_markdown(b: dict) -> str:
    lines = [f"# Brief: {b['primary_keyword']}", "",
             f"- Intent: **{b['intent']}**  |  Theme: {b['theme']}  |  Pillar page: {'this page' if b['is_pillar'] else b['pillar_keyword']}",
             f"- Cluster volume: {b['total_volume']}/mo (synthetic)  |  Avg difficulty: {b['avg_difficulty']}",
             f"- Target length: ~{b['target_words']} words", f"- Suggested schema: {b['schema']}", "",
             f"**Meta title ({len(b['meta_title'])} chars):** {b['meta_title']}", "",
             f"**Meta description ({len(b['meta_description'])} chars):** {b['meta_description']}", "",
             "## Also cover (secondary keywords)", ""]
    lines += [f"- {k}" for k in b["secondary_keywords"]] or ["- (none)"]
    lines += ["", "## Suggested outline", ""]
    lines += [f"{i}. {h}" for i, h in enumerate(b["outline"], 1)]
    lines += ["", "## Internal links", ""]
    il = b["internal_links"]
    if il["up"]:
        lines.append(f"- Link up to pillar: {il['up']}")
    lines += [f"- Link across to: {k}" for k in il["across"]]
    return "\n".join(lines) + "\n"
