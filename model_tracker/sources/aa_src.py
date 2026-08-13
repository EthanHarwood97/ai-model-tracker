from .. import aa as aa_parsers


def fetch_coding(f):
    r = f.get("https://artificialanalysis.ai/agents/coding-agents")
    return aa_parsers.scrape_coding(r.text)


def fetch_models(f):
    r = f.get("https://artificialanalysis.ai/leaderboards/models")
    return aa_parsers.scrape_models(r.text)


def fetch_changelog(f):
    r = f.get("https://artificialanalysis.ai/changelog")
    entries = aa_parsers.scrape_changelog(r.text)
    rows = []
    for e in entries:
        rows.append({
            "kind": "changelog",
            "name": e["title"],
            "slug": None,
            "score": None,
            "extra": {"date": e.get("date")},
        })
    return rows
