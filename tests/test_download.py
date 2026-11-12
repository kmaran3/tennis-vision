"""Offline checks for download failures, ZIP imports, and inventory accuracy."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("download", Path(__file__).resolve().parents[1] / "ingest/download.py")
download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download)


class DownloadChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = self.root / "data/source-lock.json"
        self.lock.parent.mkdir()
        self.lock.write_text("{}")
        self.root_patch = patch.object(download, "ROOT", self.root)
        self.lock_patch = patch.object(download, "LOCK", self.lock)
        self.root_patch.start()
        self.lock_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.lock_patch.stop)
        self.source = {"id": "fixture", "method": "github", "group": "core", "repo": "example/fixture",
                       "url": "https://github.com/example/fixture", "destination": "data/raw/fixture",
                       "required_patterns": ["matches.csv"]}

    def archive(self, entries):
        path = self.root / "fixture.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            for name, value in entries.items():
                bundle.writestr(name, value)
        return path

    def test_browser_import_keeps_data_and_records_unverified_revision(self):
        archive = self.archive({"fixture-main/matches.csv": "id\n1\n", "fixture-main/LICENSE": "original notice"})
        with patch.object(download, "request", side_effect=AssertionError("network must not be used")):
            download.fetch_github(self.source, archive)
        directory = self.root / self.source["destination"]
        self.assertEqual((directory / "LICENSE").read_text(), "original notice")
        receipt = json.loads((directory / ".download.json").read_text())
        self.assertIsNone(receipt["revision"])
        self.assertEqual(receipt["imported_archive_sha256"], download.digest(archive))
        self.assertEqual(json.loads(self.lock.read_text()), {})

    def test_missing_required_files_do_not_publish_a_partial_snapshot(self):
        archive = self.archive({"fixture-main/README.md": "metadata only"})
        with self.assertRaisesRegex(ValueError, "missing required"):
            download.fetch_github(self.source, archive)
        self.assertFalse((self.root / self.source["destination"]).exists())

    def test_automatic_fetch_uses_and_locks_an_immutable_commit(self):
        archive = self.archive({"fixture-commit/matches.csv": "id\n1\n"})
        revision = "a" * 40
        requested = []

        def fake_request(url):
            requested.append(url)
            return io.BytesIO(json.dumps({"sha": revision}).encode())

        def fake_download(url, destination):
            requested.append(url)
            destination.write_bytes(archive.read_bytes())

        with patch.object(download, "request", side_effect=fake_request), patch.object(download, "download", side_effect=fake_download):
            download.fetch_github(self.source)
        self.assertEqual(requested[-1], "https://codeload.github.com/example/fixture/zip/" + revision)
        self.assertEqual(json.loads(self.lock.read_text())["fixture"]["revision"], revision)
        receipt = json.loads((self.root / self.source["destination"] / ".download.json").read_text())
        self.assertEqual(receipt["revision"], revision)

    def test_failed_transfer_removes_partial_file(self):
        class BrokenResponse(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("connection dropped")
                return super().read(3)

        destination = self.root / "download.csv"
        with patch.object(download, "request", return_value=BrokenResponse(b"partial content")):
            with self.assertRaisesRegex(OSError, "connection dropped"):
                download.download("https://example.com/download.csv", destination)
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_suffix(".csv.part").exists())

    def test_traversal_archive_is_rejected_without_writing_outside_destination(self):
        archive = self.archive({"fixture-main/matches.csv": "id\n1\n", "fixture-main/../../escaped": "bad"})
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
            download.fetch_github(self.source, archive)
        self.assertFalse((self.root / "escaped").exists())

    def test_cached_snapshot_detects_modified_files(self):
        download.fetch_github(self.source, self.archive({"fixture-main/matches.csv": "id\n1\n"}))
        (self.root / self.source["destination"] / "matches.csv").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Cached file changed"):
            download.fetch_github(self.source)

    def test_http_error_page_is_not_an_odds_csv(self):
        path = self.root / "odds.csv"
        path.write_text("<!doctype html><html>Access denied</html>")
        with self.assertRaisesRegex(ValueError, "HTML"):
            download.validate_odds(path)

    def test_semicolon_odds_with_required_columns_are_accepted(self):
        path = self.root / "odds.csv"
        path.write_text("date;joueur1;joueur2;cote1_cloture;cote2_cloture\n2024-01-01;A;B;1.5;2.8\n")
        download.validate_odds(path)

    def test_inventory_fails_for_a_missing_odds_season(self):
        source = {"id": "odds", "method": "season_csv", "group": "core", "first_year": 2021,
                  "destination": "data/raw/odds", "download_template": "https://example.com/odds-{year}.csv"}
        destination = self.root / source["destination"]
        destination.mkdir(parents=True)
        (destination / "odds-2021.csv").write_text("placeholder")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(download.inventory([source], True, 2022), 1)
        result = json.loads((self.root / "data/inventory.json").read_text())
        self.assertEqual(result["sources"][0]["missing_patterns"], ["odds-2022.csv"])


if __name__ == "__main__":
    unittest.main()
