"""Tests for site_render.py (releases.json -> index.html)."""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import site_render as site

REPO_ROOT = Path(__file__).resolve().parents[4]


def _rel(project="pdia", version="11.0.0.3", build="312", **kw):
    stem = f"pentaho-suite/sbom-pdia-{version}-{build}"
    rel = {
        "project": project,
        "version": version,
        "build": build,
        "date": "2026-10-07",
        "components": 2281,
        "zip": {"path": f"{stem}.zip", "size": 5811096},
        "pdf": {"path": f"{stem}.pdf", "size": 585083},
    }
    rel.update(kw)
    return rel


_HTML = """<div class="stats">
        <div class="stat"><strong>9</strong><span>Products</span></div>
        <div class="stat"><strong>99</strong><span>Current releases</span></div>
</div>
<tbody>
<!-- project:pdia -->
stale
<!-- /project:pdia -->
</tbody>
"""


class TestVersionKey(unittest.TestCase):
    def test_numeric_segments(self):
        self.assertGreater(site.version_key("10.2.0.10"), site.version_key("10.2.0.9"))
        self.assertGreater(site.version_key("11.0.0.0"), site.version_key("10.2.0.10"))

    def test_mixed_segments_do_not_crash(self):
        self.assertGreater(site.version_key("1.0.1"), site.version_key("1.0.0-rc.1"))
        self.assertIsNotNone(site.version_key("c99927d"))


class TestHumanSize(unittest.TestCase):
    def test_matches_published_labels(self):
        self.assertEqual(site.human_size(5811096), "5.5 MB")
        self.assertEqual(site.human_size(20403088), "19.5 MB")
        self.assertEqual(site.human_size(1727368), "1.6 MB")
        self.assertEqual(site.human_size(585083), "571 KB")
        self.assertEqual(site.human_size(101444), "99 KB")
        self.assertEqual(site.human_size(53916), "53 KB")


class TestOrderingAndLatest(unittest.TestCase):
    def test_sorted_newest_first_across_lines(self):
        rels = [_rel(version="10.2.0.9", build="418"), _rel(version="11.0.0.0", build="237"),
                _rel(version="10.2.0.10", build="438")]
        self.assertEqual([r["version"] for r in site.sort_releases(rels)],
                         ["11.0.0.0", "10.2.0.10", "10.2.0.9"])

    def test_latest_per_release_line(self):
        rels = [_rel(version="11.0.0.3", build="312"), _rel(version="11.0.0.2", build="294"),
                _rel(version="10.2.0.10", build="438"), _rel(version="10.2.0.9", build="418")]
        latest = site.latest_keys(rels)
        self.assertEqual(sorted(k[1] for k in latest), ["10.2.0.10", "11.0.0.3"])

    def test_latest_is_per_project(self):
        rels = [_rel(version="0.7.1", build="353"),
                _rel(project="pdi-openlineage-plugin-ee", version="0.7.0", build="292")]
        self.assertEqual(len(site.latest_keys(rels)), 2)

    def test_same_version_newer_build_wins(self):
        rels = [_rel(version="11.0.0.3", build="99"), _rel(version="11.0.0.3", build="312")]
        self.assertEqual(site.latest_keys(rels), {("pdia", "11.0.0.3", "312")})
        self.assertEqual([r["build"] for r in site.sort_releases(rels)], ["312", "99"])


class TestRenderIndex(unittest.TestCase):
    def test_replaces_block_and_stats(self):
        out = site.render_index(_HTML, [_rel()])
        self.assertNotIn("stale", out)
        self.assertIn('<span class="version">11.0.0.3</span><span class="latest">Latest</span>', out)
        self.assertIn("<strong>1</strong><span>Products</span>", out)
        self.assertIn("<strong>1</strong><span>Current releases</span>", out)
        self.assertIn('<td class="num">2,281</td>', out)
        self.assertIn("ZIP <small>5.5 MB</small>", out)

    def test_values_are_html_escaped(self):
        out = site.render_index(_HTML, [_rel(build="<b>")])
        self.assertIn("&lt;b&gt;", out)
        self.assertNotIn("<b>", out)

    def test_unknown_project_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "project:nope"):
            site.render_index(_HTML, [_rel(project="nope")])

    def test_is_idempotent(self):
        once = site.render_index(_HTML, [_rel()])
        self.assertEqual(site.render_index(once, [_rel()]), once)


class TestValidateReleases(unittest.TestCase):
    def test_duplicate_zip_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            site.validate_releases([_rel(), _rel()])

    def test_missing_field_rejected(self):
        rel = _rel()
        del rel["date"]
        with self.assertRaisesRegex(ValueError, "date"):
            site.validate_releases([rel])


class TestRoundTrip(unittest.TestCase):
    def test_load_save_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "releases.json"
            rels = [_rel(version="10.2.0.9", build="418"), _rel()]
            site.save_releases(path, rels)
            first = path.read_text()
            site.save_releases(path, site.load_releases(path))
            self.assertEqual(path.read_text(), first)
            self.assertEqual(json.loads(first)["releases"][0]["version"], "11.0.0.3")


class TestRepositoryIsInSync(unittest.TestCase):
    """index.html must be exactly what releases.json renders to."""

    def test_index_matches_releases_json(self):
        html = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
        releases = site.load_releases(REPO_ROOT / "releases.json")
        self.assertEqual(site.render_index(html, releases), html)

    def test_every_published_file_exists_with_recorded_size(self):
        for rel in site.load_releases(REPO_ROOT / "releases.json"):
            for kind in ("zip", "pdf"):
                path = REPO_ROOT / rel[kind]["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.stat().st_size, rel[kind]["size"], path)

    def test_input_not_mutated(self):
        releases = site.load_releases(REPO_ROOT / "releases.json")
        before = copy.deepcopy(releases)
        site.render_index((REPO_ROOT / "index.html").read_text(encoding="utf-8"), releases)
        self.assertEqual(releases, before)


if __name__ == "__main__":
    unittest.main()
