import csv
import datetime as dt
from pathlib import Path

import pytest

from seo_engine import audit, briefs, calendar, keywords, links, performance
from seo_engine.cli import run_all

DATA = Path(__file__).parent.parent / "data"


# ---------- intent ----------
@pytest.mark.parametrize("kw,intent", [
    ("how to use a moka pot", "informational"),
    ("best burr grinder", "commercial"),
    ("espresso machine vs drip brewer", "commercial"),
    ("buy espresso machine", "transactional"),
    ("cheap cold brew", "transactional"),
    ("bean atlas login", "navigational"),
    ("cold brew", "informational"),  # default bucket
])
def test_classify_intent(kw, intent):
    assert keywords.classify_intent(kw) == intent


def test_navigational_beats_transactional():
    assert keywords.classify_intent("bean atlas coffee beans price") == "navigational"


# ---------- clustering / pillars ----------
@pytest.fixture(scope="module")
def clusters():
    return keywords.build_clusters(keywords.load_keywords(str(DATA / "keywords.csv")))


def test_every_keyword_in_exactly_one_cluster(clusters):
    total = sum(len(c.keywords) for c in clusters)
    assert total == len(keywords.load_keywords(str(DATA / "keywords.csv")))


def test_clusters_are_single_intent_single_theme(clusters):
    for c in clusters:
        assert {k.intent for k in c.keywords} == {c.intent}
        assert {k.theme for k in c.keywords} == {c.theme}


def test_known_themes_found(clusters):
    themes = {c.theme for c in clusters}
    assert {"espresso machine", "cold brew", "french press", "burr grinder"} <= themes


def test_primary_is_highest_volume(clusters):
    for c in clusters:
        assert c.primary.volume == max(k.volume for k in c.keywords)


def test_pillars_exclude_brand_and_include_all_themes(clusters):
    pillars = keywords.plan_pillars(clusters)
    assert "brand" not in {p.theme for p in pillars}
    assert len(pillars) >= 6
    for p in pillars:
        assert len(p.keyword.split()) <= 3


# ---------- briefs ----------
def test_brief_fields_and_limits(clusters):
    pillars = keywords.plan_pillars(clusters)
    p = pillars[0]
    for c in p.clusters:
        if c.intent == "navigational":
            continue
        b = briefs.make_brief(c, p)
        assert len(b["meta_title"]) <= 60 and len(b["meta_description"]) <= 155
        assert b["outline"] and b["target_words"] >= 250
        assert "# Brief:" in briefs.brief_to_markdown(b)


def test_harder_keywords_get_longer_briefs():
    assert briefs.target_words("commercial", 70) > briefs.target_words("commercial", 30)


# ---------- audit ----------
GOOD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>A Reasonable Page Title For Testing Here</title>
<meta name="description" content="%s"><link rel="canonical" href="https://example.invalid/x">
<script src="a.js" defer></script>
<script type="application/ld+json">{"@type":"Article"}</script></head><body><h1>Hello</h1>
<h2>Sub</h2><p>%s</p><img src="a.jpg" alt="a" width="10" height="10"><a href="/other.html">other page</a></body></html>""" % (
    "d" * 100, "word " * 400)


def test_audit_clean_page_has_no_errors_or_warnings():
    r = audit.audit_html(GOOD)
    assert not [f for f in r.findings if f.severity != "info"], r.findings
    assert r.score >= 99
    assert r.word_count >= 400 and r.internal_links == ["/other.html"]


def test_audit_detects_problems():
    r = audit.audit_html("<html><head><script src='x.js'></script></head><body><h2>x</h2><img src='a.jpg'><a href='/p'>click here</a></body></html>")
    checks = {f.check for f in r.findings}
    assert {"title", "meta_description", "h1", "word_count", "schema", "image_alt", "cls_image_dimensions",
            "render_blocking_script", "viewport", "lang", "anchor_text"} <= checks
    assert r.score < 40


def test_audit_invalid_jsonld_and_multiple_h1():
    html = GOOD.replace('{"@type":"Article"}', '{"@type": ').replace("<h2>Sub</h2>", "<h1>Two</h1>")
    checks = {(f.check, f.severity) for f in audit.audit_html(html).findings}
    assert ("schema", "error") in checks and ("h1", "warn") in checks


def test_audit_external_links_not_internal():
    r = audit.audit_html(GOOD.replace("/other.html", "https://elsewhere.invalid/x"))
    assert r.internal_links == []


def test_audit_site_has_spread_of_scores():
    scores = {r.path: r.score for r in audit.audit_dir(str(DATA / "site"))}
    assert scores["/how-to-use-espresso-machine.html"] > 90
    assert scores["/cold-brew-tips.html"] < 40


# ---------- links ----------
def test_link_recommender_skips_existing_and_self():
    results = audit.audit_dir(str(DATA / "site"))
    targets = links.load_targets(str(DATA / "pages.csv"))
    sugs = links.recommend(results, targets)
    assert sugs
    existing = {r.path: {h for h in r.internal_links} for r in results}
    for s in sugs:
        assert s.source != s.target
        assert s.target not in existing[s.source]
        assert s.anchor.lower() == targets[s.target]


def test_orphans_found():
    results = audit.audit_dir(str(DATA / "site"))
    assert "/moka-pot-tips.html" in links.orphans(results)
    assert "/espresso-machine-guide.html" not in links.orphans(results)


# ---------- calendar ----------
def test_calendar_pillars_first_and_on_publish_days(clusters):
    pillars = keywords.plan_pillars(clusters)
    rows = calendar.build_calendar(pillars, dt.date(2026, 12, 1))
    n_pillars = sum(r["type"] == "pillar" for r in rows)
    assert [r["type"] for r in rows[:n_pillars]] == ["pillar"] * n_pillars
    for r in rows:
        assert dt.date.fromisoformat(r["publish_date"]).weekday() in (1, 3)
    dates = [r["publish_date"] for r in rows]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    assert len({r["slug"] for r in rows}) == len(rows)


# ---------- performance ----------
def _row(day, page, clicks, impr, pos, q="q"):
    return {"date": day, "page": page, "query": q, "clicks": clicks, "impressions": impr, "position": pos}


def test_performance_flags():
    end = dt.date(2026, 4, 28)
    rows = []
    for i in range(56):
        d = end - dt.timedelta(days=i)
        recent = i < 28
        rows.append(_row(d, "/decay", 1 if recent else 4, 100, 4.0))        # clicks fall 75%
        rows.append(_row(d, "/snippet", 1, 100, 3.0))                      # pos 3, ctr 1% vs 10% expected
        rows.append(_row(d, "/near", 3, 100, 12.0))                        # striking distance
        rows.append(_row(d, "/ok", 10, 100, 3.0))                          # healthy
    a = performance.analyse(rows)
    flags = {r["page"]: r["flags"] for r in a["pages"]}
    assert "decaying" in flags["/decay"]
    assert "low-ctr-for-position" in flags["/snippet"]
    assert "striking-distance" in flags["/near"]
    assert flags["/ok"] == []
    assert "Recommended actions" in performance.report_markdown(a)


def test_performance_aggregates_ctr_and_weighted_position():
    s = performance.aggregate([_row(dt.date(2026, 1, 1), "/a", 5, 100, 2.0), _row(dt.date(2026, 1, 2), "/a", 5, 300, 6.0)])["/a"]
    assert s.ctr == 10 / 400 and s.position == pytest.approx(5.0)


# ---------- end to end ----------
def test_run_all_writes_everything(tmp_path):
    summary = run_all(DATA, tmp_path, dt.date(2026, 12, 1))
    for f in ["clusters.csv", "editorial_calendar.csv", "audit.md", "link_suggestions.csv", "performance.md"]:
        assert (tmp_path / f).stat().st_size > 0
    assert len(list((tmp_path / "briefs").glob("*.md"))) == summary["briefs"] > 0
    with open(tmp_path / "editorial_calendar.csv") as f:
        assert len(list(csv.DictReader(f))) == summary["calendar_rows"]


def test_data_generation_is_deterministic(tmp_path):
    import generate_data
    a = (DATA / "keywords.csv").read_text()
    generate_data.ROOT = tmp_path
    generate_data.main()
    assert (tmp_path / "keywords.csv").read_text() == a
    assert (tmp_path / "gsc.csv").read_text() == (DATA / "gsc.csv").read_text()
