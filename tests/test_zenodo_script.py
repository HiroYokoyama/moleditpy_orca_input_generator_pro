"""The Zenodo archive script, driven end to end against a fake Zenodo.

Two production failures live here as regressions:

1. The v1.2.0 archive step died on ``{"status": 400, "message": "Invalid value
   gpl-3.0."}`` -- the script echoes the parent record's stored licence id back
   to the API, and this record still carries the pre-SPDX ``gpl-3.0``.
2. That failure happened *after* the files were committed, so the retry then hit
   an already-populated draft, where re-registering a key is another 400.

The script is loaded from its path (it lives in scripts/, not in the package)
and every HTTP call is served by a stub, so nothing here touches the network.
"""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "update_zenodo.py",
)
_spec = importlib.util.spec_from_file_location(
    "_update_zenodo_under_test", _MODULE_PATH
)
update_zenodo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_zenodo)

DRAFT_ID = "99999"
RECORD_ID = "12345"
BASE = "https://zenodo.org/api"
DRAFT_SELF = f"{BASE}/records/{DRAFT_ID}/draft"
DRAFT_FILES = f"{DRAFT_SELF}/files"


class FakeZenodo:
    """Minimal InvenioRDM stand-in that records every request it serves."""

    def __init__(
        self, parent_license="gpl-3.0", draft_entries=None, files_shape="list"
    ):
        self.parent_license = parent_license
        self.draft_entries = draft_entries or {}
        # "list" is what production returns; "dict" is the documented RDM shape.
        self.files_shape = files_shape
        self.calls = []  # (method, url)
        self.put_metadata = None
        self.registered = None
        self.published = False

    def handle(self, request):
        method = request.get_method()
        url = request.full_url
        self.calls.append((method, url))
        body = request.data

        if method == "POST" and url.endswith(f"/records/{RECORD_ID}/versions"):
            return {
                "id": DRAFT_ID,
                "links": {
                    "self": DRAFT_SELF,
                    "files": DRAFT_FILES,
                    "publish": f"{DRAFT_SELF}/actions/publish",
                },
            }
        if method == "GET" and url == DRAFT_SELF:
            if self.files_shape == "list":
                return {"files": [{"key": key} for key in self.draft_entries]}
            return {"files": {"entries": self.draft_entries}}
        if method == "GET" and url == DRAFT_FILES:
            return {"entries": [{"key": key} for key in self.draft_entries]}
        if method == "DELETE" and url.startswith(DRAFT_FILES + "/"):
            self.draft_entries.pop(url.rsplit("/", 1)[-1], None)
            return b""
        if method == "POST" and url == DRAFT_FILES:
            self.registered = json.loads(body.decode())
            return {}
        if method == "PUT" and url.endswith("/content"):
            return {}
        if method == "POST" and url.endswith("/commit"):
            return {}
        if method == "GET" and url == f"{BASE}/records/{RECORD_ID}":
            return {
                "metadata": {
                    "title": "Test Record",
                    "version": "1.1.2",
                    "license": {"id": self.parent_license},
                    "resource_type": {"type": "software"},
                    "creators": [{"name": "Yokoyama, Hiromichi"}],
                }
            }
        if method == "PUT" and url == DRAFT_SELF:
            self.put_metadata = json.loads(body.decode())
            return {}
        if method == "POST" and url.endswith("/actions/publish"):
            self.published = True
            return {"doi": "10.5281/zenodo.99999"}
        raise AssertionError(f"unexpected request: {method} {url}")

    def urlopen(self, request, *args, **kwargs):
        payload = self.handle(request)
        if not isinstance(payload, bytes):
            payload = json.dumps(payload).encode()
        response = io.BytesIO(payload)
        response.__enter__ = lambda: response
        response.__exit__ = lambda *exc: False
        return response


class ZenodoScriptTestCase(unittest.TestCase):
    def run_script(
        self, fake, argv_extra=(), files=("dist/app.zip", "dist/source.tar.gz")
    ):
        argv = [
            "update_zenodo.py",
            "--token",
            "fake-token",
            "--deposition-id",
            RECORD_ID,
            "--version-string",
            "v1.2.0",
            *argv_extra,
            *files,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch("urllib.request.urlopen", fake.urlopen),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", lambda *a, **k: io.BytesIO(b"payload")),
        ):
            update_zenodo.main()


class TestLicenceNormalisation(ZenodoScriptTestCase):
    def test_legacy_gpl3_is_mapped_to_spdx(self):
        fake = FakeZenodo(parent_license="gpl-3.0")
        self.run_script(fake, argv_extra=["--publish"])
        rights = fake.put_metadata["metadata"]["rights"]
        self.assertEqual(rights, [{"id": "gpl-3.0-or-later"}])

    def test_already_spdx_id_is_untouched(self):
        fake = FakeZenodo(parent_license="mit")
        self.run_script(fake)
        self.assertEqual(fake.put_metadata["metadata"]["rights"], [{"id": "mit"}])

    def test_other_legacy_families_are_mapped(self):
        for legacy, spdx in (
            ("gpl-2.0", "gpl-2.0-or-later"),
            ("lgpl-3.0", "lgpl-3.0-or-later"),
            ("agpl-3.0", "agpl-3.0-or-later"),
        ):
            with self.subTest(legacy=legacy):
                fake = FakeZenodo(parent_license=legacy)
                self.run_script(fake)
                self.assertEqual(
                    fake.put_metadata["metadata"]["rights"], [{"id": spdx}]
                )


class TestRetryAgainstAPopulatedDraft(ZenodoScriptTestCase):
    def test_files_left_by_a_failed_run_are_dropped_before_registering(self):
        fake = FakeZenodo(
            draft_entries={
                "app.zip": {"key": "app.zip"},
                "source.tar.gz": {"key": "source.tar.gz"},
            }
        )
        self.run_script(fake)
        deletes = [url for method, url in fake.calls if method == "DELETE"]
        self.assertEqual(
            sorted(deletes),
            sorted([f"{DRAFT_FILES}/app.zip", f"{DRAFT_FILES}/source.tar.gz"]),
        )
        # Every file is still registered and uploaded after the cleanup.
        self.assertEqual(
            fake.registered, [{"key": "app.zip"}, {"key": "source.tar.gz"}]
        )

    def test_deletion_precedes_registration(self):
        fake = FakeZenodo(draft_entries={"app.zip": {"key": "app.zip"}})
        self.run_script(fake)
        methods = [(m, u) for m, u in fake.calls if m == "DELETE" or u == DRAFT_FILES]
        self.assertEqual(methods[0][0], "DELETE")

    def test_unrelated_draft_files_are_left_alone(self):
        fake = FakeZenodo(draft_entries={"leftover.pdf": {"key": "leftover.pdf"}})
        self.run_script(fake)
        self.assertEqual([m for m, _ in fake.calls if m == "DELETE"], [])

    def test_clean_draft_issues_no_deletes(self):
        fake = FakeZenodo()
        self.run_script(fake)
        self.assertEqual([m for m, _ in fake.calls if m == "DELETE"], [])

    def test_the_documented_dict_shape_works_too(self):
        fake = FakeZenodo(
            draft_entries={"app.zip": {"key": "app.zip"}}, files_shape="dict"
        )
        self.run_script(fake)
        self.assertEqual(
            [url for m, url in fake.calls if m == "DELETE"],
            [f"{DRAFT_FILES}/app.zip"],
        )


class TestExistingDraftFiles(unittest.TestCase):
    def test_dict_entries(self):
        draft = {"files": {"entries": {"a.zip": {"key": "a.zip"}}}}
        self.assertEqual(
            update_zenodo.existing_draft_files(draft, DRAFT_FILES, {}), ["a.zip"]
        )

    def test_list_entries(self):
        draft = {"files": {"entries": [{"key": "a.zip"}, {"nokey": 1}]}}
        self.assertEqual(
            update_zenodo.existing_draft_files(draft, DRAFT_FILES, {}), ["a.zip"]
        )

    def test_absent_entries_are_fetched_from_the_files_endpoint(self):
        with patch.object(
            update_zenodo, "make_request", return_value={"entries": [{"key": "b.zip"}]}
        ) as fetch:
            self.assertEqual(
                update_zenodo.existing_draft_files({}, DRAFT_FILES, {}), ["b.zip"]
            )
        fetch.assert_called_once()

    def test_files_as_a_bare_list(self):
        # What production actually returned; the dict-only version raised
        # AttributeError: 'list' object has no attribute 'get'.
        draft = {"files": [{"key": "a.zip"}, {"key": "source.tar.gz"}]}
        self.assertEqual(
            update_zenodo.existing_draft_files(draft, DRAFT_FILES, {}),
            ["a.zip", "source.tar.gz"],
        )

    def test_empty_draft_body_falls_back_to_the_files_endpoint(self):
        draft = {"files": []}
        with patch.object(
            update_zenodo, "make_request", return_value=[{"key": "b.zip"}]
        ):
            self.assertEqual(
                update_zenodo.existing_draft_files(draft, DRAFT_FILES, {}), ["b.zip"]
            )

    def test_unexpected_shape_is_not_fatal(self):
        draft = {"files": {"entries": "nonsense"}}
        with patch.object(update_zenodo, "make_request", return_value="nonsense"):
            self.assertEqual(
                update_zenodo.existing_draft_files(draft, DRAFT_FILES, {}), []
            )

    def test_a_failed_listing_does_not_abort_the_upload(self):
        with patch.object(
            update_zenodo, "make_request", side_effect=RuntimeError("HTTP Error 404")
        ):
            self.assertEqual(
                update_zenodo.existing_draft_files({}, DRAFT_FILES, {}), []
            )


class TestVersionGuard(ZenodoScriptTestCase):
    def test_publishing_the_parent_version_again_is_refused(self):
        fake = FakeZenodo()
        with self.assertRaises(ValueError):
            argv = [
                "update_zenodo.py",
                "--token",
                "t",
                "--deposition-id",
                RECORD_ID,
                "--version-string",
                "v1.1.2",
                "--publish",
                "dist/app.zip",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch("urllib.request.urlopen", fake.urlopen),
                patch("os.path.exists", return_value=True),
                patch("builtins.open", lambda *a, **k: io.BytesIO(b"payload")),
            ):
                update_zenodo.main()


if __name__ == "__main__":
    unittest.main()
