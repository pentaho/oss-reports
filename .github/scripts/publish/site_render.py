#!/usr/bin/env python3
"""Render the dynamic parts of index.html from releases.json.

releases.json is the source of truth for every published CycloneDX release.
Each product table body in index.html is delimited by
``<!-- project:{key} -->`` / ``<!-- /project:{key} -->`` markers; everything
between them is regenerated (newest first, ``Latest`` badge on the newest
release of each release line), as are the hero's product and release counts.
The rest of index.html is hand-maintained.

Usage: site_render.py [--check]   (--check fails if index.html is out of date)
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_FIELDS = ("project", "version", "build", "date", "components", "zip", "pdf")
# Release files are not deployed to Pages; they are served from the repository.
RAW_BASE = "https://raw.githubusercontent.com/pentaho/oss-reports/main/"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_ZIP_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v3h16v-3"/></svg>')
_PDF_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M9 13h6M9 17h6"/></svg>')
_SHIELD_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                '<path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z"/>'
                '<path d="M9 12l2 2 4-4"/></svg>')


def version_key(value: str) -> tuple:
    parts = re.split(r"[.\-+_]", str(value))
    return tuple((1, int(p), "") if p.isdigit() else (0, 0, p) for p in parts)


def release_line(version: str) -> str:
    return ".".join(str(version).split(".")[:2])


def _sort_key(rel: dict) -> tuple:
    return version_key(rel["version"]), version_key(rel["build"])


def sort_releases(releases: list) -> list:
    return sorted(releases, key=_sort_key, reverse=True)


def latest_keys(releases: list) -> set:
    newest: dict = {}
    for rel in releases:
        line = (rel["project"], release_line(rel["version"]))
        if line not in newest or _sort_key(rel) > _sort_key(newest[line]):
            newest[line] = rel
    return {(r["project"], r["version"], r["build"]) for r in newest.values()}


def human_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{round(size / 1024)} KB"


def validate_releases(releases: list) -> None:
    seen = set()
    for rel in releases:
        for field in REQUIRED_FIELDS:
            if field not in rel:
                raise ValueError(f"release {rel.get('zip', rel)} is missing '{field}'")
        for kind in ("zip", "pdf"):
            if not rel[kind].get("path") or not isinstance(rel[kind].get("size"), int):
                raise ValueError(f"release {rel['version']} needs {kind}.path and {kind}.size")
            if not _SHA256_RE.match(str(rel[kind].get("sha256", ""))):
                raise ValueError(f"release {rel['version']} needs a lowercase hex {kind}.sha256")
        if rel["zip"]["path"] in seen:
            raise ValueError(f"duplicate release {rel['zip']['path']}")
        seen.add(rel["zip"]["path"])


def load_releases(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        releases = json.load(f)["releases"]
    validate_releases(releases)
    return releases


def save_releases(path: Path, releases: list) -> None:
    validate_releases(releases)
    ordered = sorted(sort_releases(releases), key=lambda r: r["project"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"releases": ordered}, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _checksums(rel: dict, label: str) -> str:
    pid = "sha-" + re.sub(r"[^a-z0-9]+", "-",
                          f"{rel['project']}-{rel['version']}-{rel['build']}".lower()).strip("-")
    entries = "".join(
        f'<dt>{name}</dt><dd><code>{rel[kind]["sha256"]}</code>'
        f'<button type="button" class="copy" data-copy="{rel[kind]["sha256"]}" '
        f'aria-label="Copy {name} SHA-256">Copy</button></dd>'
        for kind, name in (("zip", "CycloneDX ZIP"), ("pdf", "PDF report"))
    )
    return (
        f'<button type="button" class="sha-btn" popovertarget="{pid}" '
        f'style="anchor-name: --{pid}" title="SHA-256 checksums" '
        f'aria-label="SHA-256 checksums for {label}">{_SHIELD_ICON}</button>'
        f'<div class="sha-pop" id="{pid}" popover style="position-anchor: --{pid}">'
        f'<p class="sha-title">SHA-256 &middot; {label}</p><dl>{entries}</dl>'
        '<p class="sha-hint">Verify a download with <code>shasum -a 256 &lt;file&gt;</code></p></div>'
    )


def _row(rel: dict, latest: bool) -> str:
    e = lambda v: html.escape(str(v), quote=True)  # noqa: E731
    label = f"{e(rel['version'])} build {e(rel['build'])}"
    badge = '<span class="latest">Latest</span>' if latest else ""
    return (
        "            <tr>\n"
        f'              <td><span class="version">{e(rel["version"])}</span>{badge}</td>\n'
        f'              <td class="build">{e(rel["build"])}</td>\n'
        f'              <td class="date">{e(rel["date"])}</td>\n'
        f'              <td class="num">{int(rel["components"]):,}</td>\n'
        f'              <td class="center"><a class="btn btn-json" href="{RAW_BASE}{e(rel["zip"]["path"])}" '
        f'aria-label="Download CycloneDX JSON for {label}">{_ZIP_ICON}'
        f'ZIP <small>{human_size(rel["zip"]["size"])}</small></a></td>\n'
        f'              <td class="center"><a class="btn btn-pdf" href="{RAW_BASE}{e(rel["pdf"]["path"])}" '
        f'aria-label="Download PDF report for {label}">{_PDF_ICON}'
        f'PDF <small>{human_size(rel["pdf"]["size"])}</small></a></td>\n'
        f'              <td class="verify">{_checksums(rel, label)}</td>\n'
        "            </tr>\n"
    )


def _replace_stat(text: str, label: str, value: int) -> str:
    pattern = re.compile(rf"<strong>[^<]*</strong><span>{re.escape(label)}</span>")
    if not pattern.search(text):
        raise ValueError(f"index.html has no '{label}' hero stat")
    return pattern.sub(f"<strong>{value}</strong><span>{label}</span>", text, count=1)


def render_index(text: str, releases: list) -> str:
    validate_releases(releases)
    latest = latest_keys(releases)
    markers = re.findall(r"<!-- project:(\S+) -->", text)
    missing = sorted({r["project"] for r in releases} - set(markers))
    if missing:
        raise ValueError(f"index.html has no <!-- project:{missing[0]} --> marker")
    for project in markers:
        rows = "".join(
            _row(r, (r["project"], r["version"], r["build"]) in latest)
            for r in sort_releases([r for r in releases if r["project"] == project])
        )
        pattern = re.compile(
            rf"(<!-- project:{re.escape(project)} -->\n).*?(<!-- /project:{re.escape(project)} -->)",
            re.S,
        )
        text = pattern.sub(lambda m: m.group(1) + rows + m.group(2), text, count=1)
    text = _replace_stat(text, "Products", len({r["project"] for r in releases}))
    return _replace_stat(text, "Current releases", len(releases))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render index.html from releases.json")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if index.html differs from what releases.json renders")
    args = parser.parse_args(argv)
    index = REPO_ROOT / "index.html"
    current = index.read_text(encoding="utf-8")
    rendered = render_index(current, load_releases(REPO_ROOT / "releases.json"))
    if args.check:
        if rendered != current:
            print("index.html is out of date: run .github/scripts/publish/site_render.py",
                  file=sys.stderr)
            return 1
        return 0
    index.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
