import json
import pathlib
import re

_OVERRIDES_PATH = pathlib.Path(__file__).resolve().parent / "aliases.json"


def load_aliases():
    if _OVERRIDES_PATH.exists():
        with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


ALIASES = load_aliases()

ORG_WORDS = {
    "anthropic", "openai", "google", "xai", "alibaba", "meta",
    "moonshot", "zhipu", "minimax", "cohere", "nvidia",
    "amazon", "microsoft", "bytedance", "seed", "01ai", "zai", "reka",
    "mosaic", "databricks", "allenai", "ibm", "salesforce", "baidu",
    "tencent", "inflection", "perplexity", "liquid", "orion", "orionai",
    "writer", "youcom", "wolfram", "huggingface", "hf", "deci",
    "eleutherai", "microsoft", "ai21labs", "bigcode", "mistralai",
    "google", "meta-llama", "deepseek-ai", "xiaomi",
}

EFFORT_WORDS = {
    "max", "xhigh", "high", "medium", "low", "none", "thinking",
    "adaptive reasoning", "max effort", "xhigh effort", "high effort",
    "medium effort", "low effort", "with fallback", "fallback",
    "non reasoning", "reasoning", "preview", "flash thinking",
    "ultra",
}

_REASONING_NOISE = re.compile(r"\([^()]*?(?:effort|reasoning|fallback|thinking)[^()]*\)", re.IGNORECASE)

FAMILY_PATTERNS = [
    ("fable", re.compile(r"\bfable[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("claude-old", re.compile(r"\bclaude[\s-]*(\d{1,2}(?:[.-]\d+)?)[\s-]*opus\b")),
    ("opus", re.compile(r"\bopus[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("sonnet", re.compile(r"\bsonnet[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("haiku", re.compile(r"\bhaiku[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("gpt", re.compile(r"\bgpt[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)(?:\s*[-/]?\s*(sol|terra|luna|mini|nano|flash|pro|max))?")),
    ("grok", re.compile(r"\bgrok[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("gemini", re.compile(r"\bgemini[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)[\s-]*(flash|pro|ultra|light|lite|nano|turbo)?")),
    ("deepseek", re.compile(r"\bdeepseek[\s-]*v?(\d{1,2}(?:[.-]\d+)?)(?!\d)[\s-]*(r1|chat|flash|pro|coder|reasoner|v3)?[\s-]*(\d{4,8})?")),
    ("kimi", re.compile(r"\bkimi[\s-]*k?(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("glm", re.compile(r"\bglm[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("qwen", re.compile(r"\bqwen[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)[\s-]*(max|plus|turbo|omni|coder|flash|vl|thinking)?")),
    ("muse", re.compile(r"\bmuse[\s-]+([a-z]+)[\s-]*(\d{1,2}(?:[.-]\d+)?)?")),
    ("solar", re.compile(r"\bsolar[\s-]*(?:pro[\s-]*)?(\d{1,2}(?:[.-]\d+)?)?")),
    ("nemotron", re.compile(r"\bnemotron[\s-]*([a-z0-9]+(?:[.-][a-z0-9]+)*)")),
    ("exaone", re.compile(r"\b(?:k-)?exaone[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("ling", re.compile(r"\bling[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("motif", re.compile(r"\bmotif[\s-]*(\d{1,2}(?:[.-]\d+)?)?")),
    ("composer", re.compile(r"\bcomposer[\s-]*(\d{1,2}(?:[.-]\d+)?)")),
    ("command", re.compile(r"\bcommand[\s-]*r?(\d+[+-]?|\w+)")),
    ("llama", re.compile(r"\bllama[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("ministral", re.compile(r"\bministral[\s-]*(\d+)?")),
    ("pixtral", re.compile(r"\bpixtral[\s-]*(\d+)?")),
    ("reka", re.compile(r"\breka[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("granite", re.compile(r"\bgranite[\s-]*([a-z0-9]+(?:[.-][a-z0-9]+)*)")),
    ("yi", re.compile(r"\byi[\s-]*(large|medium|small)?[-\s]*([a-z0-9.]*)")),
    ("ernie", re.compile(r"\bernie[\s-]*(\d{1,2}(?:[.-]\d+)?)(?!\d)")),
    ("hunyuan", re.compile(r"\bhunyuan[\s-]*([a-z0-9.-]*)")),
    ("doubao", re.compile(r"\bdoubao[\s-]*([a-z0-9.-]*)")),
    ("minimax", re.compile(r"\bminimax[\s-]*([a-z0-9.-]*)")),
    ("k2", re.compile(r"\ba\.x-k2\b|\bk2[\s-]*thinker")),
]

ORG_STRIP_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(ORG_WORDS, key=len, reverse=True)) + r")[\s-]*")


def _norm_version(v):
    return v.replace("-", ".").replace("_", ".")


def canon(name):
    if not name:
        return None
    s = str(name).lower().strip()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = _REASONING_NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9.\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = ORG_STRIP_RE.sub(" ", s).strip()
    if not s:
        return None
    for key, pat in FAMILY_PATTERNS:
        m = pat.search(s)
        if not m:
            continue
        if key == "k2":
            return "ax-k2" if "a.x" in s else "k2"
        if key == "claude-old":
            return "opus" + _norm_version(m.group(1))
        if key == "muse":
            out = "muse" + m.group(1)
            if m.group(2):
                out += _norm_version(m.group(2))
            return out
        groups = [g for g in m.groups() if g]
        if not groups:
            return key
        ver = _norm_version(groups[0])
        out = key + ver
        if len(groups) > 1 and groups[1]:
            out += "-" + groups[1]
        if len(groups) > 2 and groups[2]:
            out += "-" + groups[2]
        return out
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] if s else None


def canon_with_effort(name, effort=None, with_fallback=False):
    base = canon(name)
    if not base:
        return None
    if effort:
        base += "-" + effort
    if with_fallback:
        base += "-fallback"
    return base


def slug_for_row(row):
    name = row.get("name") or ""
    c = canon(name)
    if c:
        return c
    extra = row.get("extra") or {}
    for hint in ("canon", "model_key", "slug"):
        v = extra.get(hint)
        if v:
            c = canon(v)
            if c:
                return c
    return canon_with_effort(
        name,
        effort=extra.get("effort"),
        with_fallback=extra.get("with_fallback", False),
    )


def plain_key(slug):
    for suf in ("-fallback",):
        if slug and slug.endswith(suf):
            slug = slug[: -len(suf)]
    parts = slug.split("-") if slug else []
    if parts and parts[-1] in {"max", "xhigh", "high", "medium", "low", "none"}:
        return "-".join(parts[:-1])
    return slug


def effort_of(slug):
    if not slug:
        return None
    if slug.endswith("-fallback"):
        slug = slug[: -len("-fallback")]
    parts = slug.split("-")
    return parts[-1] if parts and parts[-1] in {"max", "xhigh", "high", "medium", "low", "none"} else None
