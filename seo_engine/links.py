"""Internal-link recommender: find unlinked mentions of other pages' target phrases."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass

from .audit import AuditResult


@dataclass
class LinkSuggestion:
    source: str
    target: str
    anchor: str
    reason: str


def load_targets(path: str) -> dict[str, str]:
    with open(path, newline="") as f:
        return {r["path"]: r["target_keyword"].strip().lower() for r in csv.DictReader(f)}


def _norm(href: str) -> str:
    return "/" + href.split("#")[0].split("?")[0].lstrip("/")


def recommend(results: list[AuditResult], targets: dict[str, str], max_per_page: int = 3) -> list[LinkSuggestion]:
    """Suggest source -> target when the source text contains the target's phrase
    verbatim and the source does not already link there. Orphans are served first."""
    existing = {r.path: {_norm(h) for h in r.internal_links} for r in results}
    inbound = {t: 0 for t in targets}
    for src, outs in existing.items():
        for o in outs:
            if o in inbound and o != src:
                inbound[o] += 1
    suggestions: list[LinkSuggestion] = []
    for src in results:
        picked = 0
        order = sorted(targets, key=lambda t: (inbound[t], t))  # fewest inbound links first
        for tgt in order:
            if tgt == src.path or tgt in existing[src.path]:
                continue
            phrase = targets[tgt]
            m = re.search(r"\b" + re.escape(phrase) + r"\b", src.text, flags=re.I)
            if m and picked < max_per_page:
                reason = "target page has no inbound internal links" if inbound[tgt] == 0 else "unlinked mention of target phrase"
                suggestions.append(LinkSuggestion(src.path, tgt, m.group(0), reason))
                picked += 1
    return suggestions


def orphans(results: list[AuditResult]) -> list[str]:
    linked = {_norm(h) for r in results for h in r.internal_links if _norm(h) != r.path}
    return sorted(r.path for r in results if r.path not in linked)


def suggestions_to_rows(sugs: list[LinkSuggestion]) -> list[dict]:
    return [{"source": s.source, "target": s.target, "anchor_text": s.anchor, "reason": s.reason} for s in sugs]
