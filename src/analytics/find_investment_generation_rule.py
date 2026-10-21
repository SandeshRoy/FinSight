
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SEARCH_TERMS = [
    "Investment Income",
    "investment income",
    "2500000",
    "investment_income",
]

SKIP_DIRS = {
    ".venv", ".git", "__pycache__", "node_modules",
    "output", "data"
}

EXTENSIONS = {".py", ".sql", ".json", ".yaml", ".yml", ".toml", ".csv"}

matches_found = 0

print("Searching project source files for investment-credit rules...\n")

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue

    if any(part in SKIP_DIRS for part in path.parts):
        continue

    if path.suffix.lower() not in EXTENSIONS:
        continue

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        continue

    for line_number, line in enumerate(lines, start=1):
        if any(term.lower() in line.lower() for term in SEARCH_TERMS):
            print(f"\nFile: {path.relative_to(ROOT)}")
            print(f"Line {line_number}: {line.strip()}")
            matches_found += 1

            # Show nearby lines to reveal the surrounding rule
            start = max(0, line_number - 4)
            end = min(len(lines), line_number + 3)

            for i in range(start, end):
                print(f"  {i + 1}: {lines[i].rstrip()}")

print(f"\nTotal matching lines: {matches_found}")
