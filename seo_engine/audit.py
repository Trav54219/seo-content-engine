"""Static on-page audit of local HTML files.

Only checks that can be done without a browser or network. The "Core Web Vitals"
checks are static proxies (missing image dimensions -> CLS risk, render-blocking
scripts -> LCP/INP risk), not measured CWV values.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SEVERITY_POINTS = {"error": 12, "warn": 5, "info": 1}


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonical = None
        self.headings: list[tuple[int, str]] = []
        self.images: list[dict] = []
        self.links: list[dict] = []
        self.head_scripts: list[dict] = []
        self.text: list[str] = []
        self._stack: list[str] = []
        self._buf = ""
        self._cur_link: dict | None = None
        self._in_head = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._stack.append(tag)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "head":
            self._in_head = True
        elif tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key.lower()] = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "img":
            self.images.append(a)
        elif tag == "script":
            if a.get("type") != "application/ld+json" and self._in_head and a.get("src"):
                self.head_scripts.append(a)
        elif tag == "a" and a.get("href"):
            self._cur_link = {"href": a["href"], "text": ""}
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "title"):
            self._buf = ""

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
        elif tag == "a" and self._cur_link:
            self.links.append(self._cur_link)
            self._cur_link = None
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((int(tag[1]), self._buf.strip()))
        elif tag == "title":
            self.title = self._buf.strip()
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        elif tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        self._buf += data
        if self._cur_link is not None:
            self._cur_link["text"] += data
        if self._stack and self._stack[-1] not in ("script", "style", "title"):
            self.text.append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ("meta", "link", "img", "br", "hr", "input"):
            self.handle_endtag(tag)


def _extract_jsonld(html: str) -> list[str]:
    return re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, flags=re.S | re.I)


@dataclass
class Finding:
    severity: str  # error | warn | info
    check: str
    message: str


@dataclass
class AuditResult:
    path: str
    title: str
    word_count: int
    internal_links: list[str]
    findings: list[Finding] = field(default_factory=list)
    text: str = ""

    @property
    def score(self) -> int:
        return max(0, 100 - sum(SEVERITY_POINTS[f.severity] for f in self.findings))


def is_internal(href: str) -> bool:
    return not re.match(r"^(https?:)?//|^mailto:|^tel:|^#", href)


def audit_html(html: str, path: str = "page.html") -> AuditResult:
    p = _Page()
    p.feed(html)
    text = " ".join(" ".join(p.text).split())
    words = len(re.findall(r"\b\w+\b", text))
    internal = [l["href"] for l in p.links if is_internal(l["href"])]
    r = AuditResult(path, p.title, words, internal, text=text)
    add = lambda sev, chk, msg: r.findings.append(Finding(sev, chk, msg))

    # --- title / meta
    if not p.title:
        add("error", "title", "Missing <title>.")
    elif len(p.title) < 30:
        add("warn", "title", f"Title is short ({len(p.title)} chars; aim for 30-60).")
    elif len(p.title) > 60:
        add("warn", "title", f"Title may truncate in results ({len(p.title)} chars; aim for 30-60).")
    desc = p.meta.get("description", "")
    if not desc:
        add("error", "meta_description", "Missing meta description.")
    elif len(desc) < 70:
        add("warn", "meta_description", f"Meta description is short ({len(desc)} chars; aim for 70-160).")
    elif len(desc) > 160:
        add("warn", "meta_description", f"Meta description is long ({len(desc)} chars; aim for 70-160).")
    if not p.canonical:
        add("warn", "canonical", "No canonical link.")
    if not p.lang:
        add("warn", "lang", "<html> has no lang attribute.")
    if "og:title" not in p.meta:
        add("info", "open_graph", "No og:title (affects social previews).")

    # --- headings
    h1s = [h for h in p.headings if h[0] == 1 and h[1]]
    if not h1s:
        add("error", "h1", "No H1 found.")
    elif len(h1s) > 1:
        add("warn", "h1", f"{len(h1s)} H1 elements; use exactly one.")
    prev = 0
    for level, _ in p.headings:
        if prev and level > prev + 1:
            add("info", "heading_order", f"Heading level jumps from H{prev} to H{level}.")
            break
        prev = level

    # --- content
    if words < 300:
        add("error" if words < 150 else "warn", "word_count", f"Thin content: {words} words.")

    # --- links
    if not internal:
        add("warn", "internal_links", "No internal links out of this page.")
    for l in p.links:
        if is_internal(l["href"]) and l["text"].strip().lower() in {"click here", "here", "read more", "more", "link"}:
            add("info", "anchor_text", f"Generic anchor text '{l['text'].strip()}' -> {l['href']}.")

    # --- schema
    blocks = _extract_jsonld(html)
    if not blocks:
        add("warn", "schema", "No JSON-LD structured data.")
    for b in blocks:
        try:
            data = json.loads(b)
            if "@type" not in data:
                add("warn", "schema", "JSON-LD present but has no @type.")
        except json.JSONDecodeError:
            add("error", "schema", "JSON-LD block is not valid JSON.")

    # --- static Core-Web-Vitals-style proxies
    no_alt = [i for i in p.images if "alt" not in i]
    if no_alt:
        add("warn", "image_alt", f"{len(no_alt)} image(s) missing alt text.")
    no_dim = [i for i in p.images if not (i.get("width") and i.get("height"))]
    if no_dim:
        add("warn", "cls_image_dimensions", f"{len(no_dim)} image(s) without width/height (layout-shift risk).")
    blocking = [s for s in p.head_scripts if "defer" not in s and "async" not in s and s.get("type") != "module"]
    if blocking:
        add("warn", "render_blocking_script", f"{len(blocking)} render-blocking script(s) in <head> (LCP/INP risk).")
    if len(p.images) > 1 and not any(i.get("loading") == "lazy" for i in p.images[1:]):
        add("info", "lazy_loading", "Below-the-fold images are not lazy-loaded.")
    if "viewport" not in p.meta:
        add("error", "viewport", "No viewport meta (mobile rendering).")
    kb = len(html.encode()) / 1024
    if kb > 200:
        add("warn", "html_size", f"HTML is {kb:.0f} KB; consider trimming.")
    return r


def audit_dir(site_dir: str) -> list[AuditResult]:
    return [audit_html(f.read_text(), "/" + f.name) for f in sorted(Path(site_dir).glob("*.html"))]


def audit_to_markdown(results: list[AuditResult]) -> str:
    out = ["# On-page audit", "", "| Page | Score | Errors | Warnings | Words |", "|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: r.score):
        e = sum(f.severity == "error" for f in r.findings)
        w = sum(f.severity == "warn" for f in r.findings)
        out.append(f"| {r.path} | {r.score} | {e} | {w} | {r.word_count} |")
    for r in sorted(results, key=lambda r: r.score):
        out += ["", f"## {r.path} (score {r.score})", ""]
        out += [f"- **{f.severity}** `{f.check}`: {f.message}" for f in r.findings] or ["- No issues found."]
    return "\n".join(out) + "\n"
