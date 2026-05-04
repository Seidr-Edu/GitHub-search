#!/usr/bin/env python3
"""
Analyze exported GitHub repositories with the CodeTabs LOC API.

This script reads a repository list exported by github_repo_search_export.py,
requests per-language LOC data for each repository, and computes Java-focused
summary fields such as Java LOC share and whether Java is the main language.

Examples:
  python3 scripts/github_repo_java_loc_analysis.py \
    --input java-repos2.json \
    --output java-repos2-loc.json

  python3 scripts/github_repo_java_loc_analysis.py \
    --input java-repos2.json \
    --output java-repos2-loc.csv \
    --format csv \
    --min-java-share 0.5
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


CODETABS_API_URL = "https://api.codetabs.com/v1/loc"
DEFAULT_SLEEP_SECONDS = 5.5
DEFAULT_TIMEOUT_SECONDS = 60


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read an exported GitHub repository list and compute Java LOC metrics "
            "using the CodeTabs LOC API."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSON or CSV file containing repositories.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON or CSV file for the analysis result.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv"),
        help="Output format. If omitted, inferred from the output file extension.",
    )
    parser.add_argument(
        "--min-java-share",
        type=float,
        help="Optional filter threshold from 0.0 to 1.0. Keep only repositories with at least this Java LOC share.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help=(
            "Delay between CodeTabs requests. Default: "
            f"{DEFAULT_SLEEP_SECONDS} seconds."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout for each CodeTabs request. Default: {DEFAULT_TIMEOUT_SECONDS} seconds.",
    )
    parser.add_argument(
        "--branch",
        help="Optional branch name to pass to CodeTabs for every repository.",
    )
    parser.add_argument(
        "--ignored",
        action="append",
        default=[],
        help="File or directory name to ignore. Repeat for multiple values.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if one repository fails instead of recording an error row.",
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


def read_input(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".json":
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return parse_json_input(data)

    if suffix == ".csv":
        with open(path, "r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            repositories = [row for row in reader]
        return repositories, {}

    raise SystemExit("Unsupported input format. Use a .json or .csv input file.")


def parse_json_input(data: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("repositories"), list):
        repositories = data["repositories"]
        metadata = {
            key: value for key, value in data.items() if key != "repositories"
        }
        return repositories, metadata

    if isinstance(data, list):
        return data, {}

    raise SystemExit(
        "Unsupported JSON input structure. Expected either an object with a repositories list or a top-level list."
    )


def normalize_repo_name(repository: dict[str, Any]) -> str:
    for key in ("name", "full_name", "repo", "repository"):
        value = repository.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"Could not determine repository name from row: {repository!r}")


def normalize_repo_url(repository: dict[str, Any], repo_name: str) -> str:
    url = repository.get("url") or repository.get("html_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return f"https://github.com/{repo_name}"


def build_codetabs_url(repo_name: str, branch: str | None, ignored: list[str]) -> str:
    params = {"github": repo_name}
    if branch:
        params["branch"] = branch
    cleaned_ignored = [value.strip() for value in ignored if value.strip()]
    if cleaned_ignored:
        params["ignored"] = ",".join(cleaned_ignored)
    return f"{CODETABS_API_URL}?{urllib.parse.urlencode(params)}"


def fetch_codetabs_loc(url: str, timeout_seconds: float) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "github-repo-java-loc-analysis-script",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected CodeTabs response: {payload!r}")
    return payload


def find_language_row(rows: list[dict[str, Any]], language_name: str) -> dict[str, Any] | None:
    target = language_name.casefold()
    for row in rows:
        language = row.get("language")
        if isinstance(language, str) and language.casefold() == target:
            return row
    return None


def coerce_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def build_analysis_row(
    repo_name: str,
    repo_url: str,
    loc_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    java_row = find_language_row(loc_rows, "Java")
    total_row = find_language_row(loc_rows, "Total")

    language_rows = [
        row for row in loc_rows
        if isinstance(row.get("language"), str) and row["language"] != "Total"
    ]
    language_rows.sort(key=lambda row: coerce_int(row.get("linesOfCode")), reverse=True)
    top_row = language_rows[0] if language_rows else None

    java_loc = coerce_int(java_row.get("linesOfCode")) if java_row else 0
    java_lines = coerce_int(java_row.get("lines")) if java_row else 0
    java_files = coerce_int(java_row.get("files")) if java_row else 0
    total_loc = coerce_int(total_row.get("linesOfCode")) if total_row else 0
    total_lines = coerce_int(total_row.get("lines")) if total_row else 0
    total_files = coerce_int(total_row.get("files")) if total_row else 0
    top_language = top_row.get("language") if top_row else None
    top_language_loc = coerce_int(top_row.get("linesOfCode")) if top_row else 0

    java_share = (java_loc / total_loc) if total_loc else 0.0
    java_is_main_language = bool(top_language == "Java" and java_loc > 0)

    return {
        "name": repo_name,
        "url": repo_url,
        "java_files": java_files,
        "java_lines": java_lines,
        "java_loc": java_loc,
        "total_files": total_files,
        "total_lines": total_lines,
        "total_loc": total_loc,
        "java_share": round(java_share, 6),
        "java_percent": round(java_share * 100, 2),
        "java_is_main_language": java_is_main_language,
        "top_language": top_language,
        "top_language_loc": top_language_loc,
        "language_breakdown": loc_rows,
    }


def analyze_repositories(
    repositories: list[dict[str, Any]],
    branch: str | None,
    ignored: list[str],
    sleep_seconds: float,
    timeout_seconds: float,
    stop_on_error: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total_repositories = len(repositories)

    for index, repository in enumerate(repositories):
        repo_name = normalize_repo_name(repository)
        repo_url = normalize_repo_url(repository, repo_name)
        api_url = build_codetabs_url(repo_name, branch, ignored)
        progress_label = f"[{index + 1}/{total_repositories}]"
        log(f"{progress_label} Fetching LOC for {repo_name}")

        try:
            loc_rows = fetch_codetabs_loc(api_url, timeout_seconds)
            result = build_analysis_row(repo_name, repo_url, loc_rows)
            result["status"] = "ok"
            result["codetabs_url"] = api_url
            results.append(result)
            log(
                f"{progress_label} OK {repo_name} "
                f"(Java {result['java_percent']}%, main={result['java_is_main_language']})"
            )
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError) as exc:
            if stop_on_error:
                raise
            results.append(
                {
                    "name": repo_name,
                    "url": repo_url,
                    "status": "error",
                    "error": str(exc),
                    "codetabs_url": api_url,
                }
            )
            log(f"{progress_label} ERROR {repo_name}: {exc}")

        if index < len(repositories) - 1 and sleep_seconds > 0:
            log(f"{progress_label} Sleeping {sleep_seconds:.1f}s to respect the CodeTabs rate limit")
            time.sleep(sleep_seconds)

    return results


def filter_results(
    results: list[dict[str, Any]],
    min_java_share: float | None,
) -> list[dict[str, Any]]:
    if min_java_share is None:
        return results

    return [
        row for row in results
        if row.get("status") == "ok"
        and float(row.get("java_share", 0.0)) >= min_java_share
    ]


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in results if row.get("status") == "ok"]
    error_rows = [row for row in results if row.get("status") == "error"]
    java_main_rows = [row for row in ok_rows if row.get("java_is_main_language")]

    total_java_loc = sum(int(row.get("java_loc", 0)) for row in ok_rows)
    total_loc = sum(int(row.get("total_loc", 0)) for row in ok_rows)
    overall_java_share = (total_java_loc / total_loc) if total_loc else 0.0

    return {
        "repositories_analyzed": len(results),
        "successful": len(ok_rows),
        "errors": len(error_rows),
        "java_main_language_count": len(java_main_rows),
        "java_main_language_share": round(
            (len(java_main_rows) / len(ok_rows)) if ok_rows else 0.0,
            6,
        ),
        "aggregate_java_loc": total_java_loc,
        "aggregate_total_loc": total_loc,
        "aggregate_java_share": round(overall_java_share, 6),
    }


def write_json(
    output_path: str,
    source_metadata: dict[str, Any],
    results: list[dict[str, Any]],
    min_java_share: float | None,
    sleep_seconds: float,
) -> None:
    payload = {
        "source": source_metadata,
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "codetabs_api_url": CODETABS_API_URL,
        "sleep_seconds": sleep_seconds,
        "min_java_share": min_java_share,
        "result_count": len(results),
        "summary": build_summary(results),
        "repositories": results,
    }
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_csv(output_path: str, results: list[dict[str, Any]]) -> None:
    csv_rows = []
    for row in results:
        csv_row = dict(row)
        csv_row.pop("language_breakdown", None)
        csv_rows.append(csv_row)

    if not csv_rows:
        fieldnames = [
            "name",
            "url",
            "status",
            "java_loc",
            "total_loc",
            "java_percent",
            "java_is_main_language",
            "top_language",
        ]
    else:
        fieldnames = list(csv_rows[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)


def validate_args(args: argparse.Namespace) -> None:
    if args.min_java_share is not None and not (0.0 <= args.min_java_share <= 1.0):
        raise SystemExit("--min-java-share must be between 0.0 and 1.0.")
    if args.sleep_seconds < 0:
        raise SystemExit("--sleep-seconds must be non-negative.")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be greater than 0.")


def main() -> int:
    args = parse_args()
    validate_args(args)
    output_format = infer_format(args.output, args.format)
    repositories, source_metadata = read_input(args.input)
    log(f"Loaded {len(repositories)} repositories from {args.input}")
    if args.min_java_share is not None:
        log(f"Filtering final output to repositories with Java share >= {args.min_java_share:.3f}")

    results = analyze_repositories(
        repositories=repositories,
        branch=args.branch,
        ignored=args.ignored,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        stop_on_error=args.stop_on_error,
    )
    filtered_results = filter_results(results, args.min_java_share)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    log(f"Writing {len(filtered_results)} analysis rows to {args.output}")
    if output_format == "json":
        write_json(
            output_path=args.output,
            source_metadata=source_metadata,
            results=filtered_results,
            min_java_share=args.min_java_share,
            sleep_seconds=args.sleep_seconds,
        )
    else:
        write_csv(args.output, filtered_results)

    print(
        f"Analyzed {len(results)} repositories and wrote {len(filtered_results)} rows to {args.output}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
