# GitHub Repository Export And Java LOC Analysis

This project contains two small scripts:

1. `scripts/github_repo_search_export.py`
   Exports GitHub repository search results to `JSON` or `CSV`.
2. `scripts/github_repo_java_loc_analysis.py`
   Reads an exported repository list, calls the CodeTabs LOC API, and computes how much of each repository is Java.

## Requirements

- `python3`
- A GitHub token in `GITHUB_TOKEN` for the GitHub search export step

## 1. Export Repositories From GitHub Search

Use `scripts/github_repo_search_export.py` to build a GitHub repository query from explicit qualifiers and save the resulting repositories.

Example:

```bash
GITHUB_TOKEN=your_token_here python3 scripts/github_repo_search_export.py \
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
```

Useful options:

- `--format csv` to force CSV output
- `--include-metadata` to include stars, forks, language, license, size, and `pushed_at`
- `--search-term`, `--topic`, `--extra-qualifier` for more query flexibility

The export script fetches the full GitHub search result set automatically. The JSON output includes the final assembled GitHub query string for documentation and reproducibility.

GitHub search itself still has a platform cap of `1000` results per query. If your query matches more than that, the script exports the first `1000` results and reports the full match count from GitHub.

## 2. Analyze Java LOC With CodeTabs

Use `scripts/github_repo_java_loc_analysis.py` to analyze the exported repositories with the CodeTabs LOC API.

Example:

```bash
python3 scripts/github_repo_java_loc_analysis.py \
  --input java-repos.json \
  --output java-repos-loc.json
```

CSV output:

```bash
python3 scripts/github_repo_java_loc_analysis.py \
  --input java-repos.json \
  --output java-repos-loc.csv \
  --format csv
```

Filter to repositories where Java is at least 50% of LOC:

```bash
python3 scripts/github_repo_java_loc_analysis.py \
  --input java-repos.json \
  --output java-repos-java50.json \
  --min-java-share 0.5
```

Useful options:

- `--branch BRANCH_NAME` to analyze a specific branch
- `--ignored DIR_OR_FILE` to ignore files or directories in the LOC analysis
- `--resume-from EXISTING_ANALYSIS.json` to reuse successful rows from a previous LOC analysis file
- `--stop-on-error` to stop immediately if one repository fails

Resume example:

```bash
python3 scripts/github_repo_java_loc_analysis.py \
  --input java-repos.json \
  --output java-repos-loc.json \
  --resume-from java-repos-loc.json
```

If `--resume-from` is not provided and the output file already exists, the script automatically reuses successful rows from the existing output file and only analyzes missing repositories.

## CodeTabs Rate Limit

CodeTabs documents a limit of `1 request every 5 seconds`.

This matters for `scripts/github_repo_java_loc_analysis.py` because it makes one API request per repository. The script therefore defaults to:

```text
--sleep-seconds 5.5
```

That default is intentional and should normally be kept as-is or increased. Reducing it below `5` seconds increases the chance of HTTP `429` rate limit errors.

Approximate runtime:

- `50` repositories takes about `50 * 5.5 = 275` seconds, plus API response time
- that is roughly `4.5` to `6` minutes in practice depending on response speed

## Output Fields From LOC Analysis

For each repository, the analysis script computes:

- `java_loc`
- `total_loc`
- `java_percent`
- `java_is_main_language`
- `top_language`
- `top_language_loc`

The JSON output also includes the full `language_breakdown` returned by CodeTabs and a summary block with aggregate counts.

## Typical Workflow

1. Export repositories from GitHub search to `java-repos.json`
2. Run the LOC analysis on that export
3. Use `java_percent` and `java_is_main_language` to decide whether Java is the dominant language in each repository

## Notes

- The GitHub export script uses the GitHub repository search API.
- The LOC analysis script uses `https://api.codetabs.com/v1/loc?github=owner/repo`.
- CodeTabs may fail on very large repositories; their documentation mentions a max repository size of `500 MB`.
