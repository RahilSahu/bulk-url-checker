# Bulk URL Checker

A small, zero-dependency Python tool that checks a whole list of URLs
in one run and writes a clean CSV report: final URL after redirects,
status code, redirect count, response time, content type, and server
header for every entry, plus the error for anything that failed.

Built for the repetitive parts of assessment and site maintenance
work: checking that a migration did not break old links, confirming a
list of in-scope URLs is alive before testing, or watching a set of
pages after a deployment.

## Usage

Create a text file with one URL per line (blank lines and lines
starting with # are ignored), or a CSV with a "url" column:

```text
# production pages
https://example.com/
https://example.com/old-page
https://example.com/api/health
```

Then run:

```bash
python3 bulk_url_check.py urls.txt
python3 bulk_url_check.py urls.csv --output results.csv --workers 20 --timeout 15
python3 bulk_url_check.py urls.txt --json
```

Example output:

```text
Report written to report.csv
Checked 3 URLs: 2 2xx, 0 3xx (after redirects the final status is recorded), 1 4xx, 0 5xx, 0 errors
```

The CSV report has one row per input URL, in input order, with the
columns: url, final_url, status_code, redirects, response_ms,
content_type, server, error.

Concurrency is bounded (default 10 workers, maximum 50) and each
request has a timeout, so a long list does not hammer a server or
hang forever on a dead host.

## Requirements

Python 3.9 or newer. No packages to install.

## Tests

The tests run a local test server on 127.0.0.1 and check a 200 page,
a redirect, and a 404, so they work fully offline:

```bash
python3 -m unittest discover -s tests
```

## Responsible use

Only check URLs for systems you own or are authorised to test, and
respect rate limits. Keep the worker count modest against other
people's servers.

## License

MIT, see LICENSE.
