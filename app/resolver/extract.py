LINES_BEFORE = 200
LINES_AFTER = 100


def extract_snippet(log_text: str, error_marker: str = "Error|FAILED|Traceback") -> str:
    lines = log_text.splitlines()
    error_idx = _find_error_line(lines, error_marker)
    if error_idx is None:
        error_idx = len(lines) - 1

    start = max(0, error_idx - LINES_BEFORE)
    end = min(len(lines), error_idx + LINES_AFTER + 1)
    snippet = lines[start:end]

    out = []
    for i, line in enumerate(snippet):
        lineno = start + i + 1
        out.append(f"{lineno:>6}: {line}")
    return "\n".join(out)


def _find_error_line(lines: list[str], pattern: str) -> int | None:
    import re

    pat = re.compile(pattern, re.IGNORECASE)
    for i in range(len(lines) - 1, -1, -1):
        if pat.search(lines[i]):
            return i
    return None
