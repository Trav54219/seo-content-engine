"""Generate the SYNTHETIC datasets used by the demo.

Everything here is invented: a made-up home-coffee site ("Bean Atlas"), made-up
search volumes, and made-up Search Console rows. Fixed seed => reproducible.
Run:  python generate_data.py
"""
import csv
import random
from pathlib import Path

SEED = 7
ROOT = Path(__file__).parent / "data"

TOPICS = {  # topic -> base monthly volume scale
    "espresso machine": 9000, "burr grinder": 5000, "pour over": 4200,
    "cold brew": 6500, "french press": 3800, "aeropress": 2600,
    "moka pot": 2100, "coffee beans": 7000,
}
# template, intent bucket weight (volume multiplier), difficulty offset
TEMPLATES = [
    ("how to use a {t}", 0.30, -12), ("what is a {t}", 0.22, -8),
    ("{t} guide for beginners", 0.10, -5), ("{t} tips", 0.12, -10),
    ("how to clean a {t}", 0.18, -14), ("{t} not working", 0.08, -18),
    ("best {t}", 0.55, 14), ("best {t} under 200", 0.14, 8),
    ("{t} review", 0.20, 6), ("{t} vs drip brewer", 0.07, -2),
    ("{t} alternatives", 0.05, 0), ("top rated {t}", 0.09, 7),
    ("buy {t}", 0.16, 10), ("{t} price", 0.11, 6),
    ("cheap {t}", 0.09, 4), ("{t} discount code", 0.03, -6),
    ("{t} for sale", 0.05, 3), ("order {t} online", 0.03, 2),
]
EXTRA = [  # nav keywords for the fictional brand
    ("bean atlas login", 900, 3), ("bean atlas coffee", 1300, 8),
    ("bean atlas subscription", 700, 6), ("bean atlas customer service", 320, 2),
    ("bean atlas official site", 260, 2), ("bean atlas espresso machine", 480, 10),
    ("bean atlas coffee beans", 640, 12), ("bean atlas sign in", 410, 2),
]


def keywords(rng):
    rows = []
    for t, scale in TOPICS.items():
        for tpl, w, d in TEMPLATES:
            vol = max(10, int(scale * w * rng.uniform(0.6, 1.4)))
            diff = min(95, max(3, int(45 + d + rng.uniform(-9, 9) + scale / 1000)))
            rows.append((tpl.format(t=t), vol, diff))
    rows += list(EXTRA)
    return rows


PAGES = [  # slug, title, target keyword, flaw profile
    ("espresso-machine-guide", "Espresso Machine Guide for Beginners: Pull Your First Shot at Home", "espresso machine guide for beginners", "good"),
    ("how-to-use-espresso-machine", "How to Use an Espresso Machine", "how to use a espresso machine", "good"),
    ("best-burr-grinder", "Best Burr Grinders", "best burr grinder", "weak"),
    ("cold-brew-tips", "Cold Brew", "cold brew tips", "bad"),
    ("pour-over-guide", "Pour Over Guide: Ratios, Grind Size and Technique Explained Simply", "pour over guide for beginners", "good"),
    ("french-press-review", "French Press Review: Three Models Compared on Heat Retention and Clean-Up", "french press review", "weak"),
    ("moka-pot-tips", "Moka Pot Tips for a Sweeter, Less Bitter Cup of Coffee at Home", "moka pot tips", "orphan"),
]

LOREM = (
    "Grind size, water temperature, brew ratio and freshness decide most of what ends up in the cup. "
    "Start with a repeatable recipe, change one variable at a time and write down what you taste. "
    "A scale and a timer cost very little and remove most of the guesswork from home brewing. "
    "Clean equipment matters too, because old oils turn bitter and flatten the flavour of good beans. "
)


def page_html(slug, title, kw, profile, others):
    words_n = {"good": 9, "weak": 5, "bad": 1, "orphan": 6}[profile]
    body = (LOREM * words_n)
    # inject natural mentions of other pages' target phrases for the link recommender
    mentions = " ".join(f"If you are also curious, read our notes on {o[2]}." for o in others[:3])
    h1 = title.split(":")[0] if profile != "bad" else ""
    desc = {
        "good": f"A practical, tested walkthrough of {kw} with clear steps, common mistakes and honest equipment advice for home brewers.",
        "weak": f"{kw}.",
        "bad": "",
        "orphan": f"Short, practical advice on {kw} so every cup tastes sweeter and less harsh, with a few quick fixes to try.",
    }[profile]
    head = ["<!doctype html>", '<html lang="en">' if profile != "bad" else "<html>", "<head>", '<meta charset="utf-8">']
    if profile != "bad":
        head.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    head.append(f"<title>{title}</title>")
    if desc:
        head.append(f'<meta name="description" content="{desc}">')
    if profile in ("good", "orphan"):
        head.append(f'<link rel="canonical" href="https://example.invalid/{slug}">')
        head.append(f'<meta property="og:title" content="{title}">')
    if profile == "bad":
        head.append('<script src="/js/tracker.js"></script>')
    else:
        head.append('<script src="/js/app.js" defer></script>')
    if profile == "good":
        head.append('<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article",'
                    f'"headline":"{title}","author":{{"@type":"Organization","name":"Bean Atlas"}}}}</script>')
    if profile == "weak":
        head.append('<script type="application/ld+json">{"@context": "https://schema.org", "@type": "Article",</script>')
    head.append("</head>")
    out = head + ["<body>", '<nav><a href="/">Home</a></nav>']
    if h1:
        out.append(f"<h1>{h1}</h1>")
    if profile == "weak":
        out.append("<h1>Second H1 by mistake</h1>")
    out.append(f"<p>{body[: len(body)]}</p>")
    h = "h3" if profile == "weak" else "h2"
    out.append(f"<{h}>Common mistakes</{h}><p>{LOREM}</p>")
    out.append("<img src=\"/img/hero.jpg\" alt=\"Brewing setup on a kitchen counter\" width=\"800\" height=\"450\">")
    if profile in ("weak", "bad"):
        out.append('<img src="/img/a.jpg"><img src="/img/b.jpg">')
    else:
        out.append('<img src="/img/b.jpg" alt="Grind size comparison" width="800" height="450" loading="lazy">')
    if profile != "orphan" or True:
        out.append(f"<p>{mentions}</p>")
    # existing internal links
    if profile == "good":
        for o in others[:2]:
            out.append(f'<p><a href="/{o[0]}.html">{o[2]}</a></p>')
    if profile == "weak":
        out.append(f'<p><a href="/{others[0][0]}.html">click here</a></p>')
    out += ["</body>", "</html>"]
    return "\n".join(out)


def gsc(rng, pages_kw):
    """56 days of synthetic query/page rows. Page 'decaying' loses clicks in the recent half."""
    import datetime as dt
    start = dt.date(2026, 3, 1)
    shapes = {  # page index -> (base impressions/day, position, trend over period)
        0: (260, 6.2, 1.15), 1: (180, 3.4, 1.0), 2: (420, 11.5, 0.9), 3: (150, 18.0, 1.0),
        4: (200, 4.8, 0.7), 5: (310, 9.2, 1.05), 6: (60, 24.0, 1.0),
    }
    ctr_curve = {1: .28, 2: .15, 3: .10, 4: .07, 5: .055, 6: .04, 7: .03, 8: .025, 9: .02, 10: .017}
    rows = []
    for d in range(56):
        day = start + dt.timedelta(days=d)
        for i, (slug, _t, kw, _p) in enumerate(pages_kw):
            base, pos, trend = shapes[i]
            f = 1 + (trend - 1) * (d / 55)
            for q, share in ((kw, .6), (kw + " 2026", .25), ("bean atlas " + kw.split()[-1], .15)):
                imp = max(0, int(base * share * f * rng.uniform(.8, 1.2)))
                p = max(1.0, pos + rng.uniform(-.8, .8) + (0 if q == kw else 2))
                ctr = ctr_curve.get(int(round(p)), .01) * rng.uniform(.5, 1.1)
                if slug == "french-press-review":  # position fine, CTR poor (snippet problem)
                    ctr *= .35
                rows.append((day.isoformat(), f"/{slug}.html", q, round(imp * ctr), imp, round(p, 1)))
    return rows


def main():
    rng = random.Random(SEED)
    (ROOT / "site").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "keywords.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["keyword", "volume", "difficulty"])
        w.writerows(keywords(rng))
    for slug, title, kw, prof in PAGES:
        others = [p for p in PAGES if p[0] != slug]
        (ROOT / "site" / f"{slug}.html").write_text(page_html(slug, title, kw, prof, others))
    with open(ROOT / "pages.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "target_keyword"])
        for slug, _t, kw, _p in PAGES:
            w.writerow([f"/{slug}.html", kw])
    with open(ROOT / "gsc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "page", "query", "clicks", "impressions", "position"])
        w.writerows(gsc(rng, PAGES))


if __name__ == "__main__":
    main()
