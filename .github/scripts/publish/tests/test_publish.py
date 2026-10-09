"""Tests for publish.py (pdia-security run -> oss-reports release)."""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import publish
import site_render

REPO_ROOT = Path(__file__).resolve().parents[4]
PROJECTS = publish.load_projects(REPO_ROOT / "manifest.yml")


class TestParseRunId(unittest.TestCase):
    def test_plain_id(self):
        self.assertEqual(publish.parse_run_id(" 18234567890 "), 18234567890)

    def test_run_urls(self):
        base = "https://github.com/pentaho/pdia-security/actions/runs/18234567890"
        for url in (base, base + "/", base + "/attempts/2", base + "/job/5123?pr=1"):
            self.assertEqual(publish.parse_run_id(url), 18234567890, url)

    def test_other_repo_url_rejected(self):
        with self.assertRaisesRegex(ValueError, "pentaho/pdia-security"):
            publish.parse_run_id("https://github.com/evil/repo/actions/runs/1")

    def test_garbage_rejected(self):
        for value in ("", "abc", "12; rm -rf /"):
            with self.assertRaises(ValueError):
                publish.parse_run_id(value)


class TestRouteProject(unittest.TestCase):
    def test_known_builds(self):
        cases = {
            "pdia-11.0": "pdia",
            "pdia-master": "pdia",
            "pdia-containers-main": "pdia-containers",
            "pdia-containers-11.0": "pdia-containers",
            "pdia-containers-10.2": "pdia-containers",
            "pdi-openlineage-plugin-ee-release-0.7": "pdi-openlineage-plugin-ee",
            "pdi-openlineage-plugin-ee-main": "pdi-openlineage-plugin-ee",
            "pdc-docker-deployment-release": "pdc-docker-deployment",
            "pdc-docker-deployment": "pdc-docker-deployment",
        }
        for build, key in cases.items():
            self.assertEqual(publish.route_project(build, PROJECTS), key, build)

    def test_prefix_needs_dash_boundary(self):
        with self.assertRaisesRegex(ValueError, "pdiax"):
            publish.route_project("pdiax-1", PROJECTS)

    def test_longest_key_wins(self):
        projects = {"pdi": {}, "pdi-openlineage": {}}
        self.assertEqual(publish.route_project("pdi-openlineage-main", projects),
                         "pdi-openlineage")

    def test_override(self):
        self.assertEqual(publish.route_project("anything", PROJECTS, "pdia"), "pdia")
        with self.assertRaisesRegex(ValueError, "nope"):
            publish.route_project("anything", PROJECTS, "nope")


class TestDeriveRelease(unittest.TestCase):
    def test_default_pattern(self):
        self.assertEqual(publish.derive_release("11.0.0.3-312", PROJECTS["pdia"]),
                         ("11.0.0.3", "312"))
        self.assertEqual(publish.derive_release("0.7.1-353",
                                                PROJECTS["pdi-openlineage-plugin-ee"]),
                         ("0.7.1", "353"))

    def test_pdc_pattern_and_padding(self):
        self.assertEqual(publish.derive_release("release-v11.0.0-c99927d",
                                                PROJECTS["pdc-docker-deployment"]),
                         ("11.0.0.0", "c99927d"))

    def test_no_match_fails_with_hint(self):
        with self.assertRaisesRegex(ValueError, "--version"):
            publish.derive_release("nodash", PROJECTS["pdia"])

    def test_precedence_inputs_then_manifest_then_pattern(self):
        cfg = PROJECTS["pdia"]
        self.assertEqual(publish.derive_release("11.0.0.3-312", cfg,
                                                manifest_release={"version": "9", "build": "8"}),
                         ("9", "8"))
        self.assertEqual(publish.derive_release("11.0.0.3-312", cfg, version="7",
                                                manifest_release={"version": "9", "build": "8"}),
                         ("7", "8"))
        self.assertEqual(publish.derive_release("nodash", cfg, version="1.0", build="5"),
                         ("1.0", "5"))

    def test_line_breaks_and_markup_rejected(self):
        cfg = PROJECTS["pdia"]
        for bad in ("1.0\nbranch=evil", "1.0\r", "<b>", "a b", "1.0\n"):
            with self.assertRaisesRegex(ValueError, "version"):
                publish.derive_release("11.0.0.3-312", cfg, version=bad)
            with self.assertRaisesRegex(ValueError, "build"):
                publish.derive_release("11.0.0.3-312", cfg, build=bad)


class TestWriteOutputs(unittest.TestCase):
    def test_multiline_value_rejected(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            path = f.name
        self.addCleanup(os.unlink, path)
        with unittest.mock.patch.dict(os.environ, {"GITHUB_OUTPUT": path}):
            with self.assertRaisesRegex(ValueError, "line break"):
                publish._write_outputs({"title": "x\nbranch=evil"})
        self.assertEqual(Path(path).read_text(), "")

    def test_branch_name_is_git_safe(self):
        self.assertEqual(publish.branch_name("my build:x/y", "1.0-2"),
                         "publish/sbom-my-build-x_y-1.0-2")


class TestParseRunTitle(unittest.TestCase):
    def test_both_workflows(self):
        self.assertEqual(
            publish.parse_run_title("SBOM Consolidation - pdia-11.0 11.0.0.3-312"),
            ("pdia-11.0", "11.0.0.3-312"))
        self.assertEqual(
            publish.parse_run_title("Xray Build: pdc-docker-deployment-release / release-v11.0.0-c99927d"),
            ("pdc-docker-deployment-release", "release-v11.0.0-c99927d"))

    def test_unknown_title(self):
        self.assertIsNone(publish.parse_run_title("Something else"))


# -- end-to-end prepare() against a fake GitHub API ---------------------------

def _sbom_bytes(n=3, build_name="pdia-11.0", build_number="11.0.0.4-330"):
    return json.dumps({
        "bomFormat": "CycloneDX", "specVersion": "1.6",
        "metadata": {"timestamp": "2026-10-20T09:00:00Z",
                     "component": {"name": build_name, "version": build_number}},
        "components": [{"name": f"c{i}"} for i in range(n)],
    }).encode()


_PDF = b"%PDF-1.4\nfake pdf\n"


def _zip_of(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, data)
    return buf.getvalue()


class FakeGitHub:
    def __init__(self, run, artifacts, files, jobs=None):
        self.run, self.artifacts, self.files, self.jobs = run, artifacts, files, jobs or []
        self.created_pr = None

    def get_json(self, path):
        page = int(path.rsplit("page=", 1)[1]) if "&page=" in path else 1
        if "/artifacts?" in path:
            items = self.artifacts if page == 1 else []
            return {"artifacts": items, "total_count": len(self.artifacts)}
        if "/jobs?" in path:
            items = self.jobs if page == 1 else []
            return {"jobs": items, "total_count": len(self.jobs)}
        if "/actions/runs/" in path:
            return self.run
        raise AssertionError(path)

    def download(self, url, dest):
        Path(dest).write_bytes(self.files[url])


def _artifact(name, expired=False):
    return {"name": name, "expired": expired, "archive_download_url": f"https://dl/{name}"}


class _Prepare(unittest.TestCase):
    build_name, build_number = "pdia-11.0", "11.0.0.4-330"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in site_render.load_releases(REPO_ROOT / "releases.json"):
            for kind in ("zip", "pdf"):
                dest = self.root / rel[kind]["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel[kind]["path"], dest)
        for name in ("index.html", "releases.json", "manifest.yml"):
            shutil.copyfile(REPO_ROOT / name, self.root / name)
        self.sbom = _sbom_bytes(build_name=self.build_name, build_number=self.build_number)
        self.safe = publish.safe_name(self.build_name)
        stem = f"{self.safe}-{self.build_number}"
        self.names = {"sbom": f"sbom-{stem}", "pdf": f"sbom-pdf-{stem}",
                      "publish": f"sbom-publish-{stem}"}

    def manifest_json(self, **over):
        stem = f"{self.safe}-{self.build_number}"
        m = {
            "schema_version": 1,
            "build": {"name": self.build_name, "number": self.build_number, "safe_name": self.safe},
            "provenance": {"run_url": "https://github.com/pentaho/pdia-security/actions/runs/42",
                           "commit": "abc123", "run_attempt": "1"},
            "sbom": {"file": f"sbom-{stem}.cdx.json", "artifact": self.names["sbom"],
                     "sha256": hashlib.sha256(self.sbom).hexdigest(), "size": len(self.sbom),
                     "component_count": 3, "timestamp": "2026-10-20T09:00:00Z",
                     "spec_version": "1.6"},
            "pdf": {"file": f"sbom-{stem}.pdf", "artifact": self.names["pdf"],
                    "sha256": hashlib.sha256(_PDF).hexdigest(), "size": len(_PDF)},
        }
        m.update(over)
        return m

    def fake(self, with_manifest=True, manifest=None, jobs=None,
             title=None, path=".github/workflows/xray-build.yml", status="completed"):
        stem = f"{self.safe}-{self.build_number}"
        files = {
            f"https://dl/{self.names['sbom']}": _zip_of(f"sbom-{stem}.cdx.json", self.sbom),
            f"https://dl/{self.names['pdf']}": _zip_of(f"sbom-{stem}.pdf", _PDF),
        }
        arts = [_artifact(self.names["sbom"]), _artifact(self.names["pdf"]),
                _artifact(f"sbom-all-{stem}"), _artifact(f"sbom-telemetry-{stem}")]
        if with_manifest:
            files[f"https://dl/{self.names['publish']}"] = _zip_of(
                "publish.json", json.dumps(manifest or self.manifest_json()).encode())
            arts.append(_artifact(self.names["publish"]))
        run = {"id": 42, "status": status, "path": path,
               "html_url": "https://github.com/pentaho/pdia-security/actions/runs/42",
               "created_at": "2026-10-20T08:00:00Z", "head_sha": "abc123",
               "display_title": title or f"Xray Build: {self.build_name} / {self.build_number}"}
        if jobs is None:
            jobs = [{"name": "Generate a snippet SBOM and consolidate it with the build / "
                             "Consolidate SBOM", "conclusion": "success", "run_attempt": 1}]
        return FakeGitHub(run, arts, files, jobs)

    def prepare(self, gh, **kw):
        return publish.prepare(gh, 42, root=self.root, **kw)


class TestPrepareWithManifest(_Prepare):
    def test_publishes_files_and_release(self):
        result = self.prepare(self.fake())
        self.assertTrue(result["verified"])
        zip_path = self.root / "pentaho-suite" / "sbom-pdia-11.0-11.0.0.4-330.zip"
        pdf_path = self.root / "pentaho-suite" / "sbom-pdia-11.0-11.0.0.4-330.pdf"
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(zf.namelist(), ["sbom-pdia-11.0-11.0.0.4-330.cdx.json"])
            self.assertEqual(zf.read(zf.namelist()[0]), self.sbom)
        self.assertEqual(pdf_path.read_bytes(), _PDF)

        rel = result["release"]
        self.assertEqual((rel["project"], rel["version"], rel["build"], rel["date"],
                          rel["components"]),
                         ("pdia", "11.0.0.4", "330", "2026-10-20", 3))
        self.assertEqual(rel["zip"], {"path": "pentaho-suite/sbom-pdia-11.0-11.0.0.4-330.zip",
                                      "size": zip_path.stat().st_size,
                                      "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()})
        self.assertEqual(rel["pdf"]["sha256"], hashlib.sha256(_PDF).hexdigest())
        self.assertEqual(rel["source"]["run_url"],
                         "https://github.com/pentaho/pdia-security/actions/runs/42")
        self.assertEqual(rel["source"]["sbom_sha256"], hashlib.sha256(self.sbom).hexdigest())

        releases = site_render.load_releases(self.root / "releases.json")
        self.assertIn(rel, releases)
        html = (self.root / "index.html").read_text()
        self.assertEqual(site_render.render_index(html, releases), html)
        self.assertIn('<span class="version">11.0.0.4</span><span class="latest">Latest</span>', html)
        self.assertNotIn('<span class="version">11.0.0.3</span><span class="latest">', html)
        self.assertIn("<strong>11</strong><span>Current releases</span>", html)

    def test_sha_mismatch_rejected(self):
        bad = self.manifest_json()
        bad["sbom"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "sha256"):
            self.prepare(self.fake(manifest=bad))
        self.assertFalse((self.root / "pentaho-suite" / "sbom-pdia-11.0-11.0.0.4-330.zip").exists())

    def test_unsupported_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema_version"):
            self.prepare(self.fake(manifest=self.manifest_json(schema_version=2)))

    def test_already_published_requires_replace(self):
        self.prepare(self.fake())
        with self.assertRaisesRegex(ValueError, "already published"):
            self.prepare(self.fake())
        self.prepare(self.fake(), replace=True)
        releases = site_render.load_releases(self.root / "releases.json")
        self.assertEqual(sum(r["version"] == "11.0.0.4" for r in releases), 1)

    def test_overrides(self):
        rel = self.prepare(self.fake(), version="11.0.0.4-hotfix", build="331")["release"]
        self.assertEqual((rel["version"], rel["build"]), ("11.0.0.4-hotfix", "331"))

    def test_dry_run_changes_nothing(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.prepare(self.fake(), dry_run=True)
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["release"]["version"], "11.0.0.4")

    def test_wrong_workflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "workflow"):
            self.prepare(self.fake(path=".github/workflows/pr.yml"))

    def test_incomplete_run_rejected(self):
        with self.assertRaisesRegex(ValueError, "in_progress"):
            self.prepare(self.fake(status="in_progress"))

    def test_stale_manifest_from_earlier_attempt_rejected(self):
        # attempt 1 succeeded and wrote publish.json; attempt 2 re-ran consolidation and failed
        jobs = [{"name": "Consolidate SBOM", "conclusion": "failure", "run_attempt": 2}]
        with self.assertRaisesRegex(ValueError, "Consolidate SBOM"):
            self.prepare(self.fake(jobs=jobs))
        jobs = [{"name": "Consolidate SBOM", "conclusion": "success", "run_attempt": 2}]
        with self.assertRaisesRegex(ValueError, "attempt"):
            self.prepare(self.fake(jobs=jobs))

    def test_rerun_of_other_jobs_keeps_manifest_valid(self):
        jobs = [{"name": "Consolidate SBOM", "conclusion": "success", "run_attempt": 1},
                {"name": "Snippet CVE Scan", "conclusion": "success", "run_attempt": 2}]
        self.assertTrue(self.prepare(self.fake(jobs=jobs))["verified"])


class TestPrepareWithoutManifest(_Prepare):
    """Runs from before sbom-publish shipped: verify via the jobs API instead."""

    def _jobs(self, conclusion):
        return [{"name": "Generate a snippet SBOM and consolidate it with the build / Consolidate SBOM",
                 "conclusion": conclusion}]

    def test_fallback_publishes(self):
        result = self.prepare(self.fake(with_manifest=False, jobs=self._jobs("success")))
        rel = result["release"]
        self.assertEqual((rel["version"], rel["build"], rel["components"]), ("11.0.0.4", "330", 3))
        self.assertEqual(rel["date"], "2026-10-20")
        self.assertFalse(result["verified"])

    def test_failed_consolidation_rejected(self):
        with self.assertRaisesRegex(ValueError, "Consolidate SBOM"):
            self.prepare(self.fake(with_manifest=False, jobs=self._jobs("failure")))

    def test_consolidation_job_missing_rejected(self):
        with self.assertRaisesRegex(ValueError, "Consolidate SBOM"):
            self.prepare(self.fake(with_manifest=False, jobs=[]))

    def test_title_must_match_artifacts(self):
        with self.assertRaisesRegex(ValueError, "title"):
            self.prepare(self.fake(with_manifest=False, jobs=self._jobs("success"),
                                   title="SBOM Consolidation - pdia-11.0 11.0.0.9-999"))


class TestPrepareGuards(_Prepare):
    def test_expired_artifact(self):
        gh = self.fake()
        for a in gh.artifacts:
            a["expired"] = True
        with self.assertRaisesRegex(ValueError, "expired"):
            self.prepare(gh)

    def test_empty_sbom_rejected(self):
        self.sbom = _sbom_bytes(n=0)
        with self.assertRaisesRegex(ValueError, "no components"):
            self.prepare(self.fake())

    def test_oversized_zip_rejected(self):
        original = publish.MAX_FILE_BYTES
        publish.MAX_FILE_BYTES = 10
        self.addCleanup(setattr, publish, "MAX_FILE_BYTES", original)
        with self.assertRaisesRegex(ValueError, "100 MB"):
            self.prepare(self.fake())
        self.assertFalse((self.root / "pentaho-suite" / "sbom-pdia-11.0-11.0.0.4-330.zip").exists())


class TestGitHubRetry(unittest.TestCase):
    def _error(self, code):
        return publish.urllib.error.HTTPError("https://api", code, "x", {}, io.BytesIO(b""))

    def test_get_retries_transient_5xx(self):
        ok = io.BytesIO(b'{"id": 1}')
        with unittest.mock.patch.object(publish.urllib.request, "urlopen",
                                        side_effect=[self._error(502), ok]) as urlopen, \
                unittest.mock.patch.object(publish.time, "sleep"):
            self.assertEqual(publish.GitHub("t").get_json("/x"), {"id": 1})
        self.assertEqual(urlopen.call_count, 2)

    def test_client_errors_and_posts_are_not_retried(self):
        gh = publish.GitHub("t")
        for call, code in ((lambda: gh.get_json("/x"), 404),
                           (lambda: gh.post_json("/x", {}), 502)):
            with unittest.mock.patch.object(publish.urllib.request, "urlopen",
                                            side_effect=self._error(code)) as urlopen, \
                    unittest.mock.patch.object(publish.time, "sleep"):
                with self.assertRaises(publish.urllib.error.HTTPError):
                    call()
            self.assertEqual(urlopen.call_count, 1)

    def test_token_not_forwarded_on_redirect(self):
        with unittest.mock.patch.object(publish.urllib.request, "urlopen",
                                        return_value=io.BytesIO(b"{}")) as urlopen:
            publish.GitHub("secret").get_json("/x")
        req = urlopen.call_args[0][0]
        self.assertNotIn("Authorization", req.headers)
        self.assertEqual(req.unredirected_hdrs["Authorization"], "Bearer secret")

    def test_only_https_urls_are_requested(self):
        gh = publish.GitHub("t")
        with unittest.mock.patch.object(publish.urllib.request, "urlopen") as urlopen:
            for url in ("file:///etc/passwd", "http://example.com/x", "ftp://x/y"):
                with self.assertRaisesRegex(ValueError, "https"):
                    gh.download(url, os.devnull)
        urlopen.assert_not_called()


class TestPrBody(unittest.TestCase):
    def test_contains_provenance_and_hashes(self):
        rel = {"project": "pdia", "version": "11.0.0.4", "build": "330", "date": "2026-10-20",
               "components": 2290,
               "zip": {"path": "pentaho-suite/a.zip", "size": 6000000, "sha256": "cc"},
               "pdf": {"path": "pentaho-suite/a.pdf", "size": 590000, "sha256": "bb"},
               "source": {"build_name": "pdia-11.0", "build_number": "11.0.0.4-330",
                          "run_url": "https://github.com/pentaho/pdia-security/actions/runs/42",
                          "sbom_sha256": "aa"}}
        body = publish.pr_body(rel, "Pentaho Data Integration and Analytics", verified=True)
        for needle in ("11.0.0.4", "330", "2,290", "actions/runs/42", "aa", "bb", "cc",
                       "pdia-11.0"):
            self.assertIn(needle, body)


if __name__ == "__main__":
    unittest.main()
