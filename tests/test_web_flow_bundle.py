"""DVDG-554: the committed flow debugger bundle (web/static/flow/) is served under the CSP and matches its source."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_server import ServerCase  # noqa: E402
from web import flowbundle, server  # noqa: E402

FORBIDDEN_JS = ("eval(", "new Function(")
DEV_ONLY = "agentation"


class TestBundleServed(ServerCase):
    def test_bundle_files_are_served_with_csp(self):
        for name in flowbundle.BUNDLE_FILES:
            with self.subTest(name):
                status, headers, body = self.get(f"/static/flow/{name}")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Security-Policy"], server.CSP)
                self.assertTrue(body)

    def test_static_route_allows_only_the_named_folders(self):
        for path in ("/static/flowx/flow.js", "/static/flow/sub/flow.js", "/static/flow/.hidden", "/static/flow/manifest.json"):
            with self.subTest(path):
                self.assertEqual(self.get(path)[0], 404)


class TestBundleContent(unittest.TestCase):
    def test_bundle_has_no_inline_requirements(self):
        js = (flowbundle.OUT / "flow.js").read_text()
        for bad in FORBIDDEN_JS:
            self.assertNotIn(bad, js)

    def test_committed_bundle_has_no_agentation(self):
        """DVDG-563: the feedback toolbar is a development tool; the served bundle must not carry it."""
        self.assertNotIn(DEV_ONLY, (flowbundle.OUT / "flow.js").read_text().lower())
        self.assertEqual([p.name for p in flowbundle.OUT.iterdir() if DEV_ONLY in p.name.lower()], [])

    def test_bundle_matches_source(self):
        manifest = json.loads(flowbundle.MANIFEST.read_text())
        self.assertEqual(manifest[flowbundle.HASH_KEY], flowbundle.source_hash(),
                         "web/static/flow/ is stale: run `npm run build` in web/flowapp/ and commit the result")

    def test_one_character_change_in_src_changes_the_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "flowapp"
            shutil.copytree(flowbundle.APP, app, ignore=shutil.ignore_patterns("node_modules"))
            before = flowbundle.source_hash(app)
            f = app / flowbundle.SOURCE_DIR / "App.tsx"
            f.write_text(f.read_text() + " ")
            self.assertNotEqual(flowbundle.source_hash(app), before)

    def test_tests_do_not_change_the_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "flowapp"
            shutil.copytree(flowbundle.APP, app, ignore=shutil.ignore_patterns("node_modules"))
            before = flowbundle.source_hash(app)
            (app / flowbundle.SOURCE_DIR / flowbundle.TEST_DIR / "extra.test.ts").write_text("// x\n")
            self.assertEqual(flowbundle.source_hash(app), before)


if __name__ == "__main__":
    unittest.main()
