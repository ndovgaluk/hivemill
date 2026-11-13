"""The flow debugger's committed bundle (DVDG-554): the hash that ties web/static/flow/ to its source in web/flowapp/.

`npm run build` (web/flowapp/package.json) runs `python3 ../flowbundle.py` after Vite, which writes
web/static/flow/manifest.json; tests/test_web_flow_bundle.py recomputes the hash and fails when the bundle is stale.
One definition here, so the build and the check can never disagree. CI needs no Node.
"""
import hashlib
import json
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
APP = WEB / "flowapp"
OUT = WEB / "static" / "flow"
MANIFEST = OUT / "manifest.json"
BUNDLE_FILES = ("flow.js", "flow.css")
CONFIG_FILES = ("package.json", "package-lock.json", "vite.config.ts", "tsconfig.json")
SOURCE_DIR = "src"
TEST_DIR = "__tests__"          # tests do not change the bundle
TEST_MARK = ".test."
HASH_KEY = "source_sha256"


def source_files(app=APP):
    """Every file that shapes the bundle, as sorted POSIX paths relative to the app folder."""
    src = [p for p in (app / SOURCE_DIR).rglob("*")
           if p.is_file() and TEST_DIR not in p.parts and TEST_MARK not in p.name]
    cfg = [app / n for n in CONFIG_FILES if (app / n).is_file()]
    return sorted(p.relative_to(app).as_posix() for p in src + cfg)


def source_hash(app=APP):
    h = hashlib.sha256()
    for rel in source_files(app):
        h.update(rel.encode() + b"\0" + (app / rel).read_bytes() + b"\0")
    return h.hexdigest()


def write_manifest(app=APP, out=OUT):
    missing = [n for n in BUNDLE_FILES if not (out / n).is_file()]
    if missing:
        sys.exit(f"flowbundle: build output missing: {', '.join(missing)}")
    (out / MANIFEST.name).write_text(json.dumps({HASH_KEY: source_hash(app), "files": list(BUNDLE_FILES)}, indent=2) + "\n")


if __name__ == "__main__":
    write_manifest()
