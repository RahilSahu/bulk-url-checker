#!/usr/bin/env python3
"""Bulk URL checker.

Reads a list of URLs from a text file (one per line, blank lines and
lines starting with # are skipped) or a CSV file (the first column, or
a column named "url"), checks each one with an HTTP request, follows
redirects, and records:

- the input URL and the final URL after redirects
- the HTTP status code and the number of redirects
- response time in milliseconds
- content type and Server header
- the error message when the request fails

Results go to a CSV report (report.csv by default) and a short summary
is printed: total, and how many came back 2xx, 3xx, 4xx, 5xx or as
errors. Concurrency is bounded (default 10 workers, maximum 50) so a
long list does not hammer a server.

Zero dependencies: Python 3.9+ standard library only. Only check URLs
for systems you own or are authorised to test.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

USER_AGENT = "bulk-url-check/1.0 (+https://github.com/RahilSahu/bulk-url-checker)"


@dataclass
class UrlResult:
    url: str
    final_url: str = ""
    status_code: int | None = None
    redirects: int = 0
    response_ms: float | None = None
    content_type: str = ""
    server: str = ""
    error: str = ""


class CountingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that remembers how many redirects it followed."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_urls(path: str) -> list[str]:
    """Read URLs from a .txt or .csv input file."""
    urls: list[str] = []
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            rows = [row for row in reader if row and any(cell.strip() for cell in row)]
        if not rows:
            return urls
        header = [cell.strip().lower() for cell in rows[0]]
        if "url" in header:
            idx = header.index("url")
            data_rows = rows[1:]
        elif rows[0][0].strip().lower().startswith(("http://", "https://")):
            idx = 0
            data_rows = rows
        else:  # header row with the URL in the first column under another name
            idx = 0
            data_rows = rows[1:]
        for row in data_rows:
            if len(row) > idx:
                value = row[idx].strip()
                if value and not value.startswith("#"):
                    urls.append(value)
        return urls

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if value and not value.startswith("#"):
                urls.append(value)
    return urls


def check_url(url: str, timeout: float = 10.0) -> UrlResult:
    """Check one URL and return its result record. Never raises."""
    target = url if "://" in url else "https://" + url
    result = UrlResult(url=url)
    handler = CountingRedirectHandler()
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(target, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(1024)  # a small read is enough, we are not downloading pages
            result.final_url = response.geturl()
            result.status_code = response.status
            result.content_type = response.headers.get("Content-Type", "")
            result.server = response.headers.get("Server", "")
    except urllib.error.HTTPError as exc:
        # An HTTP error status is still a successful check.
        result.final_url = exc.geturl() or target
        result.status_code = exc.code
        if exc.headers:
            result.content_type = exc.headers.get("Content-Type", "")
            result.server = exc.headers.get("Server", "")
    except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
        result.error = str(getattr(exc, "reason", exc))
        result.final_url = target
    result.redirects = handler.count
    result.response_ms = round((time.perf_counter() - started) * 1000, 1)
    return result


def check_all(urls: list[str], workers: int = 10, timeout: float = 10.0) -> list[UrlResult]:
    """Check every URL with a bounded pool, preserving input order."""
    workers = max(1, min(workers, 50))
    results: list[UrlResult | None] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_url, url, timeout): i for i, url in enumerate(urls)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [r for r in results if r is not None]


def summarise(results: list[UrlResult]) -> dict:
    summary = {"total": len(results), "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "error": 0}
    for r in results:
        if r.error or r.status_code is None:
            summary["error"] += 1
        else:
            summary[f"{r.status_code // 100}xx"] = summary.get(f"{r.status_code // 100}xx", 0) + 1
    return summary


def write_csv(results: list[UrlResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(UrlResult(url="")).keys()))
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a list of URLs and write a CSV report.")
    parser.add_argument("input", help="Text file (one URL per line) or CSV file of URLs")
    parser.add_argument("--output", default="report.csv", help="CSV report path (default report.csv)")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent checks, 1 to 50 (default 10)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print records as JSON instead of writing the CSV")
    args = parser.parse_args(argv)

    try:
        urls = read_urls(args.input)
    except OSError as exc:
        print(f"Error: could not read {args.input}: {exc}", file=sys.stderr)
        return 2
    if not urls:
        print(f"Error: no URLs found in {args.input}", file=sys.stderr)
        return 2

    results = check_all(urls, workers=args.workers, timeout=args.timeout)
    summary = summarise(results)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        write_csv(results, args.output)
        print(f"\nReport written to {args.output}")
    print(f"Checked {summary['total']} URLs: "
          f"{summary['2xx']} 2xx, {summary['3xx']} 3xx (after redirects the final status is recorded), "
          f"{summary['4xx']} 4xx, {summary['5xx']} 5xx, {summary['error']} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
