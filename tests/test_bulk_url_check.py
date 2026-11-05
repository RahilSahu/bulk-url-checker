import csv
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bulk_url_check import check_all, check_url, read_urls, write_csv


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Server", "TestServer/1.0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args):  # keep test output quiet
        pass


class BulkUrlCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_ok_status(self):
        result = check_url(f"{self.base}/ok", timeout=5)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.redirects, 0)
        self.assertEqual(result.error, "")
        self.assertIn("text/plain", result.content_type)

    def test_redirect_is_followed_and_counted(self):
        result = check_url(f"{self.base}/redirect", timeout=5)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.redirects, 1)
        self.assertTrue(result.final_url.endswith("/ok"))

    def test_unknown_path_is_404(self):
        result = check_url(f"{self.base}/no-such-page", timeout=5)
        self.assertEqual(result.status_code, 404)

    def test_csv_report_has_the_right_rows(self):
        urls = [f"{self.base}/ok", f"{self.base}/redirect", f"{self.base}/missing"]
        results = check_all(urls, workers=3, timeout=5)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.csv"
            write_csv(results, str(report))
            with open(report, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["status_code"] for row in rows], ["200", "200", "404"])
        self.assertEqual(rows[1]["redirects"], "1")
        self.assertEqual(rows[0]["url"], urls[0])

    def test_read_urls_skips_blanks_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "urls.txt"
            path.write_text("# comment line\n\nhttp://example.com/a\n  http://example.com/b  \n", encoding="utf-8")
            self.assertEqual(read_urls(str(path)), ["http://example.com/a", "http://example.com/b"])


if __name__ == "__main__":
    unittest.main()
