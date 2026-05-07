#!/usr/bin/env python3
"""
Generate a LaTeX appendix file containing repository names from a JSON export.

Examples:
  python3 scripts/generate_repo_appendix_tex.py \
    --input java-repos-sup2.json \
    --output appendix-repository-list.tex

  python3 scripts/generate_repo_appendix_tex.py \
    --input java-repos-sup2.json \
    --output appendix-repository-list.tex \
    --section-title "Supplementary Repository List" \
    --columns 3
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an appendix-ready LaTeX file listing repository names."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSON file, for example java-repos-sup2.json.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output .tex file path.",
    )
    parser.add_argument(
        "--section-title",
        default="Repository List",
        help="LaTeX section title. Default: Repository List.",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=2,
        help="Number of columns for the multicol layout. Default: 2.",
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Remove duplicate repository names before writing output.",
    )
    return parser.parse_args()


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_repo_names(payload: Any) -> list[str]:
    if isinstance(payload, dict) and isinstance(payload.get("repositories"), list):
        repositories = payload["repositories"]
    elif isinstance(payload, list):
        repositories = payload
    else:
        raise SystemExit(
            "Unsupported JSON format. Expected a top-level list or an object with a repositories list."
        )

    names: list[str] = []
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        name = repository.get("name") or repository.get("full_name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())

    return names


def latex_escape(value: str) -> str:
    text = value
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def build_tex(section_title: str, columns: int, repo_names: list[str]) -> str:
    lines = [
        rf"\section{{{latex_escape(section_title)}}}",
        rf"\begin{{multicols}}{{{columns}}}",
        r"\begin{itemize}",
    ]

    for repo_name in repo_names:
        lines.append(rf"\item \texttt{{{latex_escape(repo_name)}}}")

    lines.extend(
        [
            r"\end{itemize}",
            r"\end{multicols}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    if args.columns < 1:
        raise SystemExit("--columns must be at least 1.")

    payload = load_json(args.input)
    repo_names = extract_repo_names(payload)
    if args.deduplicate:
        repo_names = sorted(set(repo_names), key=str.casefold)
    else:
        repo_names = sorted(repo_names, key=str.casefold)

    tex = build_tex(args.section_title, args.columns, repo_names)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(tex)

    print(f"Wrote {len(repo_names)} repository names to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
