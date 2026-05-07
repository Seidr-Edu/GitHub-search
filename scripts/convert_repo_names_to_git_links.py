#!/usr/bin/env python3
"""
Convert one-column CSV files of GitHub repository names to one-column CSV files
of .git clone URLs.

Examples:
  python3 scripts/convert_repo_names_to_git_links.py \
    --input chosen.csv

  python3 scripts/convert_repo_names_to_git_links.py \
    --input chosen.csv \
    --input java-repos-sup2-only-new-in-loc-range-vs-java-repos.csv

  python3 scripts/convert_repo_names_to_git_links.py \
    --input chosen.csv \
    --output chosen-git-links.csv
"""

from __future__ import annotations

import argparse
import csv
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one-column CSV repository names to GitHub .git links."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input one-column CSV file containing repository names like owner/repo.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional output CSV path. Only valid when a single input file is provided. "
            "If omitted, outputs are created next to the inputs with a -git-links suffix."
        ),
    )
    return parser.parse_args()


def read_repo_names(path: str) -> list[str]:
    repo_names: list[str] = []
    with open(path, "r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            repo_name = row[0].strip()
            if repo_name:
                repo_names.append(repo_name)
    return repo_names


def build_git_link(repo_name: str) -> str:
    return f"https://github.com/{repo_name}.git"


def default_output_path(input_path: str) -> str:
    directory = os.path.dirname(input_path)
    filename = os.path.basename(input_path)
    stem, _ = os.path.splitext(filename)
    return os.path.join(directory, f"{stem}-git-links.csv")


def write_git_links(path: str, repo_names: list[str]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for repo_name in repo_names:
            writer.writerow([build_git_link(repo_name)])


def main() -> int:
    args = parse_args()
    if args.output and len(args.input) != 1:
        raise SystemExit("--output can only be used with a single --input file.")

    for input_path in args.input:
        output_path = args.output or default_output_path(input_path)
        repo_names = read_repo_names(input_path)
        write_git_links(output_path, repo_names)
        print(f"Wrote {len(repo_names)} git links to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
