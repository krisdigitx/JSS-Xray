#!/usr/bin/env python3
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--tag", required=True)
args = parser.parse_args()

path = Path(args.file)
lines = path.read_text().splitlines()

targets = {"backend", "frontend"}
found = set()
section = None
inside_image = False

for i, line in enumerate(lines):
    if line and not line.startswith((" ", "\t")) and line.endswith(":"):
        section = line[:-1]
        inside_image = False
        continue

    if section in targets:
        if line.strip() == "image:" and line.startswith("  "):
            inside_image = True
            continue

        if inside_image and line.startswith("    tag:"):
            lines[i] = f"    tag: {args.tag}"
            found.add(section)
            inside_image = False

missing = targets - found
if missing:
    raise SystemExit(f"Could not find image tag for: {', '.join(sorted(missing))}")

path.write_text("\n".join(lines) + "\n")
print(f"Updated backend/frontend tags to {args.tag}")
