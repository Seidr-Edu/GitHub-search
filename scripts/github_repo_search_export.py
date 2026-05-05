#!/usr/bin/env python3
"""
Export GitHub repository search results to JSON or CSV.

Examples:
  GITHUB_TOKEN=ghp_xxx python3 scripts/github_repo_search_export.py \
    --stars-min 1000 \
    --forks-min 200 \
    --pushed-after 2024-11-25 \
    --language Java \
    --license mit \
    --license apache-2.0 \
    --license bsd-3-clause \
    --license bsd-2-clause \
    --license 0bsd \
    --visibility public \
    --size-max 1000 \
    --output java-repos.json

  GITHUB_TOKEN=ghp_xxx python3 scripts/github_repo_search_export.py \
    --topic benchmark \
    --language Python \
    --output repos.csv

  GITHUB_TOKEN=ghp_xxx python3 scripts/github_repo_search_export.py \
    --search-term compiler \
    --stars-min 500 \
    --language Rust \
    --visibility public \
    --include-metadata \
    --output rust.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API_URL = "https://api.github.com/search/repositories"
API_VERSION = "2026-03-10"
MAX_SEARCH_RESULTS = 1000
REQUEST_BATCH_SIZE = 100


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export GitHub repository search results from explicit search qualifiers."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path, for example results.json or results.csv.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv"),
        help="Output format. If omitted, inferred from the output file extension.",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        help="Include stars, forks, pushed_at, license, and API URL in the export.",
    )
    parser.add_argument(
        "--token",
        help="GitHub token. If omitted, the script uses GITHUB_TOKEN from the environment.",
    )

    parser.add_argument(
        "--search-term",
        action="append",
        default=[],
        help="Unqualified search term. Repeat for multiple terms.",
    )
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        help="Repository language qualifier. Repeat for multiple values.",
    )
    parser.add_argument(
        "--license",
        action="append",
        default=[],
        help="Repository license qualifier. Repeat for multiple values.",
    )
    parser.add_argument(
        "--topic",
        action="append",
        default=[],
        help="Repository topic qualifier. Repeat for multiple values.",
    )
    parser.add_argument(
        "--visibility",
        choices=("public", "private"),
        help="Repository visibility. Mapped to is:public or is:private.",
    )
    parser.add_argument(
        "--stars-min",
        type=int,
        help="Minimum star count, mapped to stars:>=N.",
    )
    parser.add_argument(
        "--stars-max",
        type=int,
        help="Maximum star count, mapped to stars:<=N.",
    )
    parser.add_argument(
        "--forks-min",
        type=int,
        help="Minimum fork count, mapped to forks:>=N.",
    )
    parser.add_argument(
        "--forks-max",
        type=int,
        help="Maximum fork count, mapped to forks:<=N.",
    )
    parser.add_argument(
        "--size-min",
        type=int,
        help="Minimum repository size in KB, mapped to size:>=N.",
    )
    parser.add_argument(
        "--size-max",
        type=int,
        help="Maximum repository size in KB, mapped to size:<=N.",
    )
    parser.add_argument(
        "--pushed-after",
        help="Lower bound for pushed date, mapped to pushed:>=YYYY-MM-DD.",
    )
    parser.add_argument(
        "--pushed-before",
        help="Upper bound for pushed date, mapped to pushed:<=YYYY-MM-DD.",
    )
    parser.add_argument(
        "--created-after",
        help="Lower bound for created date, mapped to created:>=YYYY-MM-DD.",
    )
    parser.add_argument(
        "--created-before",
        help="Upper bound for created date, mapped to created:<=YYYY-MM-DD.",
    )
    parser.add_argument(
        "--archived",
        choices=("true", "false"),
        help="Repository archived state, mapped to archived:true or archived:false.",
    )
    parser.add_argument(
        "--fork",
        choices=("true", "only"),
        help="Fork filter, mapped to fork:true or fork:only.",
    )
    parser.add_argument(
        "--extra-qualifier",
        action="append",
        default=[],
        help="Any raw qualifier to append directly, for example topic:ml or template:false.",
    )
    return parser.parse_args()


def infer_format(output_path: str, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format

    suffix = os.path.splitext(output_path)[1].lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"

    raise SystemExit(
        "Could not infer output format from file extension. Use --format json or --format csv."
    )


def append_range(parts: list[str], name: str, minimum: int | None, maximum: int | None) -> None:
    if minimum is not None:
        parts.append(f"{name}:>={minimum}")
    if maximum is not None:
        parts.append(f"{name}:<={maximum}")


def append_multi(parts: list[str], name: str, values: list[str]) -> None:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            parts.append(f"{name}:{cleaned}")


def build_query(args: argparse.Namespace) -> str:
    parts: list[str] = []

    for term in args.search_term:
        cleaned = term.strip()
        if cleaned:
            parts.append(cleaned)

    append_range(parts, "stars", args.stars_min, args.stars_max)
    append_range(parts, "forks", args.forks_min, args.forks_max)
    append_range(parts, "size", args.size_min, args.size_max)

    if args.pushed_after:
        parts.append(f"pushed:>={args.pushed_after}")
    if args.pushed_before:
        parts.append(f"pushed:<={args.pushed_before}")
    if args.created_after:
        parts.append(f"created:>={args.created_after}")
    if args.created_before:
        parts.append(f"created:<={args.created_before}")

    append_multi(parts, "language", args.language)
    append_multi(parts, "license", args.license)
    append_multi(parts, "topic", args.topic)

    if args.visibility:
        parts.append(f"is:{args.visibility}")
    if args.archived:
        parts.append(f"archived:{args.archived}")
    if args.fork:
        parts.append(f"fork:{args.fork}")

    for qualifier in args.extra_qualifier:
        cleaned = qualifier.strip()
        if cleaned:
            parts.append(cleaned)

    if not parts:
        raise SystemExit(
            "No search qualifiers were provided. Add at least one qualifier such as --language, --stars-min, or --search-term."
        )

    return " ".join(parts)


def build_request_url(query: str, batch_index: int) -> str:
    params = {
        "q": query,
        "page": str(batch_index),
        "per_page": str(REQUEST_BATCH_SIZE),
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def github_get(url: str, token: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-repo-search-export-script",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API request failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach GitHub API: {exc}") from exc


def normalize_repo(item: dict[str, Any], include_metadata: bool) -> dict[str, Any]:
    repo = {
        "name": item["full_name"],
        "url": item["html_url"],
    }

    if include_metadata:
        license_data = item.get("license") or {}
        repo.update(
            {
                "id": item.get("id"),
                "stars": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "language": item.get("language"),
                "license": license_data.get("spdx_id") or license_data.get("key"),
                "size_kb": item.get("size"),
                "pushed_at": item.get("pushed_at"),
                "api_url": item.get("url"),
            }
        )

    return repo


def fetch_repositories(
    query: str,
    include_metadata: bool,
    token: str | None,
) -> tuple[list[dict[str, Any]], int]:
    repositories: list[dict[str, Any]] = []
    batch_index = 1
    total_count = 0
    target_count = 0

    log("Fetching GitHub repositories")
    while True:
        payload = github_get(build_request_url(query, batch_index), token)
        if batch_index == 1:
            total_count = int(payload.get("total_count", 0))
            incomplete_results = bool(payload.get("incomplete_results", False))
            if incomplete_results:
                print(
                    "Warning: GitHub reports incomplete_results=true; the result set may be partial.",
                    file=sys.stderr,
                )
            target_count = min(total_count, MAX_SEARCH_RESULTS)

        items = payload.get("items", [])
        repositories.extend(
            normalize_repo(item, include_metadata) for item in items
        )
        collected = len(repositories)
        log(
            f"Completed request {batch_index} "
            f"({collected}/{target_count if target_count else total_count} repositories collected)"
        )

        if not items:
            break
        if target_count and collected >= target_count:
            repositories = repositories[:target_count]
            break
        if len(items) < REQUEST_BATCH_SIZE:
            break

        batch_index += 1

    return repositories, total_count


def write_json(
    output_path: str,
    query: str,
    repositories: list[dict[str, Any]],
    total_count: int,
) -> None:
    payload = {
        "query": query,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result_count_exported": len(repositories),
        "total_count_reported_by_github": total_count,
        "github_search_result_cap": MAX_SEARCH_RESULTS,
        "repositories": repositories,
    }
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_csv(output_path: str, repositories: list[dict[str, Any]]) -> None:
    if not repositories:
        fieldnames = ["name", "url"]
    else:
        fieldnames = list(repositories[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(repositories)


def main() -> int:
    args = parse_args()
    output_format = infer_format(args.output, args.format)
    query = build_query(args)
    token = args.token or os.environ.get("GITHUB_TOKEN")

    log(f"Built GitHub query: {query}")
    repositories, total_count = fetch_repositories(
        query=query,
        include_metadata=args.include_metadata,
        token=token,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    log(f"Writing {len(repositories)} repositories to {args.output}")
    if output_format == "json":
        write_json(args.output, query, repositories, total_count)
    else:
        write_csv(args.output, repositories)

    capped_note = ""
    if total_count > MAX_SEARCH_RESULTS:
        capped_note = (
            f" GitHub search results are capped at {MAX_SEARCH_RESULTS}; "
            f"the export contains the first {len(repositories)} matches."
        )

    print(
        f"Exported {len(repositories)} repositories to {args.output}."
        f" GitHub reported {total_count} matching repositories for query: {query}."
        f"{capped_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
