"""Command line: python -m seo_engine <command>. All inputs are local files."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

from . import audit, briefs, calendar, keywords, links, performance


def _write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run_all(data: Path, out: Path, start: dt.date) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "briefs").mkdir(exist_ok=True)
    kws = keywords.load_keywords(str(data / "keywords.csv"))
    clusters = keywords.build_clusters(kws)
    pillars = keywords.plan_pillars(clusters)
    _write_csv(keywords.clusters_to_rows(clusters), out / "clusters.csv")
    n_briefs = 0
    for p in pillars:
        for c in p.clusters:
            if c.intent == "navigational":
                continue
            b = briefs.make_brief(c, p)
            (out / "briefs" / f"{b['slug']}.md").write_text(briefs.brief_to_markdown(b))
            n_briefs += 1
    cal = calendar.build_calendar(pillars, start)
    calendar.write_csv(cal, str(out / "editorial_calendar.csv"))
    results = audit.audit_dir(str(data / "site"))
    (out / "audit.md").write_text(audit.audit_to_markdown(results))
    sugs = links.recommend(results, links.load_targets(str(data / "pages.csv")))
    _write_csv(links.suggestions_to_rows(sugs), out / "link_suggestions.csv")
    rep = performance.analyse(performance.load_gsc(str(data / "gsc.csv")))
    (out / "performance.md").write_text(performance.report_markdown(rep))
    return {"keywords": len(kws), "clusters": len(clusters), "pillars": len(pillars), "briefs": n_briefs,
            "calendar_rows": len(cal), "pages_audited": len(results), "link_suggestions": len(sugs),
            "orphans": links.orphans(results)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="seo_engine")
    ap.add_argument("command", choices=["run-all"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="out")
    ap.add_argument("--start", default="2026-12-01", help="calendar start date (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    summary = run_all(Path(a.data), Path(a.out), dt.date.fromisoformat(a.start))
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
