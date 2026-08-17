from collections import Counter


EXPECTED_KINDS = {
    "aa_coding": {"coding_index"},
    "aa_models": {"intelligence"},
    "livebench": {"livebench_coding"},
    "lmarena": set(),
    "openrouter": {"market"},
    "deepseek": {"market"},
}


def validate_rows(source, rows):
    """Fail closed when a parser returns an empty or structurally invalid result."""
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{source} returned no rows; retaining the last good snapshot")

    kinds = Counter()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{source} row {index} is not an object")
        if not row.get("kind") or not row.get("name"):
            raise ValueError(f"{source} row {index} is missing kind or name")
        score = row.get("score")
        if score is not None:
            try:
                numeric = float(score)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{source} row {index} has a non-numeric score") from exc
            if source not in {"lmarena"} and not 0 <= numeric <= 100:
                raise ValueError(f"{source} row {index} score is outside the expected range: {numeric}")
        kinds[row["kind"]] += 1

    required = EXPECTED_KINDS.get(source, set())
    if required and not required.intersection(kinds):
        raise ValueError(f"{source} is missing expected kinds: {sorted(required)}")
    return {"rows": len(rows), "kinds": dict(kinds)}
