#!/usr/bin/env python3
"""Publish the SBOM + PDF of a pentaho/pdia-security run to this site.

  prepare  Resolve an "SBOM Consolidation" or "Xray Build" run (ID or URL),
           download its final SBOM and PDF, verify them, write
           {folder}/sbom-{safe}-{n}.zip|.pdf, add the release to releases.json
           and re-render index.html. --dry-run reports without writing.
  open-pr  Open the pull request for a pushed branch.

The run's sbom-publish-* artifact (publish.json) is preferred: it only exists
when consolidation succeeded and carries the files' SHA-256. Older runs fall
back to the jobs API and the run title.

Needs GH_TOKEN with actions:read on pentaho/pdia-security (and
pull-requests:write here for open-pr).
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import yaml

import site_render

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_REPO = "pentaho/pdia-security"
SOURCE_WORKFLOWS = (".github/workflows/consolidate-sbom.yml", ".github/workflows/xray-build.yml")
CONSOLIDATE_JOB = "Consolidate SBOM"
MANIFEST_SCHEMA_VERSION = 1
DEFAULT_VERSION_PATTERN = r"^(?P<version>.+)-(?P<build>[^-]+)$"
# GitHub rejects files over 100 MB; keep a margin.
MAX_FILE_BYTES = 95 * 1024 * 1024

_RUN_URL_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)(?:[/?#].*)?$")
# Version/build end up in file content, PR titles, branch names and step outputs.
_SAFE_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_TITLE_RES = (
    re.compile(r"^SBOM Consolidation - (?P<name>.+) (?P<number>\S+)$"),
    re.compile(r"^Xray Build: (?P<name>.+) / (?P<number>\S+)$"),
)


class GitHub:
    def __init__(self, token: str, api: str = "https://api.github.com"):
        self.token, self.api = token, api

    def _request(self, url: str, method: str = "GET", body: dict | None = None):
        if url.startswith("/"):
            url = self.api + url
        elif not url.startswith("https://"):
            raise ValueError(f"refusing to request a non-https URL: {url!r}")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        # Not forwarded on redirect: artifact downloads 302 to blob storage.
        req.add_unredirected_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for attempt in range(1, 4):
            try:
                return urllib.request.urlopen(req, timeout=300)
            except urllib.error.HTTPError as exc:
                if method != "GET" or exc.code < 500 or attempt == 3:
                    raise
                print(f"[WARN] GitHub API {exc.code}, retrying ({attempt}/3)", file=sys.stderr)
                time.sleep(5 * attempt)

    def get_json(self, path: str) -> dict:
        with self._request(path) as resp:
            return json.load(resp)

    def post_json(self, path: str, body: dict) -> dict:
        with self._request(path, "POST", body) as resp:
            return json.load(resp)

    def download(self, url: str, dest) -> None:
        with self._request(url) as resp, open(dest, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)


def safe_name(build_name: str) -> str:
    return build_name.replace(":", "-").replace("/", "_")


def branch_name(build_name: str, build_number: str) -> str:
    return re.sub(r"[^A-Za-z0-9._/-]", "-",
                  f"publish/sbom-{safe_name(build_name)}-{build_number}")


def parse_run_id(value: str) -> int:
    value = (value or "").strip()
    if value.isdigit():
        return int(value)
    match = _RUN_URL_RE.match(value)
    if not match:
        raise ValueError(f"not a run ID or run URL: {value!r}")
    if match.group(1) != SOURCE_REPO:
        raise ValueError(f"run URL must point to {SOURCE_REPO}, got {match.group(1)}")
    return int(match.group(2))


def parse_run_title(title: str):
    for pattern in _TITLE_RES:
        match = pattern.match(title or "")
        if match:
            return match.group("name"), match.group("number")
    return None


def load_projects(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["projects"]


def route_project(build_name: str, projects: dict, override: str | None = None) -> str:
    if override:
        if override not in projects:
            raise ValueError(f"unknown project {override!r}; known: {', '.join(projects)}")
        return override
    matches = [k for k in projects if build_name == k or build_name.startswith(k + "-")]
    if not matches:
        raise ValueError(f"no project in manifest.yml matches build {build_name!r}; "
                         f"pass --project ({', '.join(projects)})")
    return max(matches, key=len)


def derive_release(build_number: str, cfg: dict, version: str | None = None,
                   build: str | None = None, manifest_release: dict | None = None):
    manifest_release = manifest_release or {}
    version = version or manifest_release.get("version")
    build = build or manifest_release.get("build")
    if not (version and build):
        match = re.match(cfg.get("version_pattern") or DEFAULT_VERSION_PATTERN, build_number)
        if not match:
            raise ValueError(f"build number {build_number!r} does not match the project's "
                             "version_pattern; pass --version and --build")
        derived = match.group("version")
        segments = cfg.get("version_segments")
        if segments:
            parts = derived.split(".")
            derived = ".".join(parts + ["0"] * (segments - len(parts)))
        version, build = version or derived, build or match.group("build")
    for label, value in (("version", version), ("build", build)):
        if not _SAFE_VALUE_RE.fullmatch(value):
            raise ValueError(f"{label} {value!r} may only contain letters, digits, '.', '_', "
                             "'+' and '-'")
    return version, build


def _paginate(gh, path: str, key: str) -> list:
    items, page = [], 1
    while True:
        data = gh.get_json(f"{path}?per_page=100&page={page}")
        items.extend(data.get(key, []))
        if not data.get(key) or len(items) >= data.get("total_count", 0):
            return items
        page += 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_single_file(gh, artifact: dict, workdir: Path) -> Path:
    if artifact.get("expired"):
        raise ValueError(f"artifact {artifact['name']} has expired; re-run the "
                         "consolidation in pdia-security and publish the new run")
    archive = workdir / f"{artifact['name']}.zip"
    gh.download(artifact["archive_download_url"], archive)
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"artifact {artifact['name']} holds {len(names)} files, expected 1")
        target = workdir / Path(names[0]).name
        target.write_bytes(zf.read(names[0]))
    return target


def _check_consolidation(gh, run_id: int, manifest_attempt=None) -> None:
    """The latest attempt of the Consolidate SBOM job must have succeeded and, when
    publish.json is used, be the attempt that wrote it (a failed re-run leaves the
    earlier attempt's artifacts on the run)."""
    jobs = _paginate(gh, f"/repos/{SOURCE_REPO}/actions/runs/{run_id}/jobs", "jobs")
    found = [j for j in jobs
             if j["name"] == CONSOLIDATE_JOB or j["name"].endswith(f"/ {CONSOLIDATE_JOB}")]
    if not found or any(j.get("conclusion") != "success" for j in found):
        raise ValueError(f"the run's latest '{CONSOLIDATE_JOB}' job did not succeed")
    if manifest_attempt is not None:
        attempts = {str(j.get("run_attempt")) for j in found}
        if attempts != {str(manifest_attempt)}:
            raise ValueError(f"publish.json is from attempt {manifest_attempt} but the latest "
                             f"'{CONSOLIDATE_JOB}' job ran in attempt {', '.join(sorted(attempts))}")


def _locate(gh, run: dict, artifacts: dict, workdir: Path):
    """Return (build_name, build_number, sbom_artifact, pdf_artifact, manifest|None)."""
    published = [a for n, a in artifacts.items() if n.startswith("sbom-publish-")]
    if len(published) > 1:
        raise ValueError(f"run has {len(published)} sbom-publish-* artifacts")
    if published:
        with open(_fetch_single_file(gh, published[0], workdir), encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported publish.json schema_version "
                             f"{manifest.get('schema_version')!r}")
        try:
            sbom = artifacts[manifest["sbom"]["artifact"]]
            pdf = artifacts[manifest["pdf"]["artifact"]]
        except KeyError as exc:
            raise ValueError(f"artifact {exc} named by publish.json is missing") from None
        _check_consolidation(gh, run["id"], (manifest.get("provenance") or {}).get("run_attempt"))
        return manifest["build"]["name"], manifest["build"]["number"], sbom, pdf, manifest

    pdfs = [n for n in artifacts if n.startswith("sbom-pdf-")]
    if len(pdfs) != 1:
        raise ValueError(f"expected one sbom-pdf-* artifact, found {pdfs or 'none'} "
                         "(runs before PDF rendering was added have no PDF: re-run the "
                         "consolidation)")
    stem = pdfs[0][len("sbom-pdf-"):]
    if f"sbom-{stem}" not in artifacts:
        raise ValueError(f"artifact sbom-{stem} is missing")
    parsed = parse_run_title(run.get("display_title", ""))
    if not parsed or f"{safe_name(parsed[0])}-{parsed[1]}" != stem:
        raise ValueError(f"run title {run.get('display_title')!r} does not match "
                         f"artifact {pdfs[0]}")
    _check_consolidation(gh, run["id"])
    return parsed[0], parsed[1], artifacts[f"sbom-{stem}"], artifacts[pdfs[0]], None


def _check_size(path: Path, label: str) -> None:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{label} is {path.stat().st_size} bytes; GitHub rejects files "
                         "over 100 MB")


def prepare(gh, run_id: int, root: Path = REPO_ROOT, project: str | None = None,
            version: str | None = None, build: str | None = None,
            replace: bool = False, dry_run: bool = False) -> dict:
    run = gh.get_json(f"/repos/{SOURCE_REPO}/actions/runs/{run_id}")
    if run.get("path", "").split("@")[0] not in SOURCE_WORKFLOWS:
        raise ValueError(f"run {run_id} is from workflow {run.get('path')!r}, expected "
                         "SBOM Consolidation or Xray Build")
    if run.get("status") != "completed":
        raise ValueError(f"run {run_id} is {run.get('status')}, not completed")
    artifacts = {a["name"]: a for a in _paginate(
        gh, f"/repos/{SOURCE_REPO}/actions/runs/{run_id}/artifacts", "artifacts")}
    projects = load_projects(root / "manifest.yml")

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        build_name, build_number, sbom_art, pdf_art, manifest = _locate(
            gh, run, artifacts, workdir)
        sbom_file = _fetch_single_file(gh, sbom_art, workdir)
        pdf_file = _fetch_single_file(gh, pdf_art, workdir)
        sbom_sha, pdf_sha = _sha256(sbom_file), _sha256(pdf_file)
        if manifest:
            if sbom_sha != manifest["sbom"]["sha256"]:
                raise ValueError(f"{sbom_file.name} sha256 does not match publish.json")
            if pdf_sha != manifest["pdf"]["sha256"]:
                raise ValueError(f"{pdf_file.name} sha256 does not match publish.json")

        with open(sbom_file, encoding="utf-8") as f:
            sbom = json.load(f)
        if sbom.get("bomFormat") != "CycloneDX":
            raise ValueError(f"{sbom_file.name} is not a CycloneDX SBOM")
        components = len(sbom.get("components") or [])
        if not components:
            raise ValueError(f"{sbom_file.name} has no components")
        if manifest and manifest["sbom"].get("component_count") != components:
            raise ValueError("component count differs from publish.json")
        if pdf_file.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"{pdf_file.name} is not a PDF")

        key = route_project(build_name, projects, project)
        cfg = projects[key]
        version, build = derive_release(build_number, cfg, version, build,
                                        (manifest or {}).get("release"))
        timestamp = (sbom.get("metadata") or {}).get("timestamp") or run["created_at"]
        stem = f"{cfg['folder']}/sbom-{safe_name(build_name)}-{build_number}"

        releases = site_render.load_releases(root / "releases.json")
        existing = [r for r in releases if r["zip"]["path"] == f"{stem}.zip"]
        if existing and not replace:
            raise ValueError(f"{stem}.zip is already published; use --replace to overwrite")
        releases = [r for r in releases if r["zip"]["path"] != f"{stem}.zip"]

        zip_file = workdir / "out.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(sbom_file, f"sbom-{safe_name(build_name)}-{build_number}.cdx.json")
        _check_size(zip_file, f"{stem}.zip")
        _check_size(pdf_file, f"{stem}.pdf")

        provenance = (manifest or {}).get("provenance", {})
        release = {
            "project": key,
            "version": version,
            "build": build,
            "date": timestamp[:10],
            "components": components,
            "zip": {"path": f"{stem}.zip", "size": zip_file.stat().st_size,
                    "sha256": _sha256(zip_file)},
            "pdf": {"path": f"{stem}.pdf", "size": pdf_file.stat().st_size, "sha256": pdf_sha},
            "source": {
                "build_name": build_name,
                "build_number": build_number,
                "run_url": provenance.get("run_url") or run["html_url"],
                "commit": provenance.get("commit") or run.get("head_sha"),
                "sbom_sha256": sbom_sha,
            },
        }
        releases.append(release)
        index = root / "index.html"
        html = site_render.render_index(index.read_text(encoding="utf-8"), releases)

        if not dry_run:
            (root / cfg["folder"]).mkdir(parents=True, exist_ok=True)
            (root / f"{stem}.zip").write_bytes(zip_file.read_bytes())
            (root / f"{stem}.pdf").write_bytes(pdf_file.read_bytes())
            site_render.save_releases(root / "releases.json", releases)
            index.write_text(html, encoding="utf-8")

    return {
        "release": release,
        "verified": manifest is not None,
        "product": cfg.get("name", key),
        "replaced": bool(existing),
        "branch": branch_name(build_name, build_number),
        "title": f"Publish {cfg.get('name', key)} {version} build {build} SBOM",
    }


def pr_body(rel: dict, product: str, verified: bool) -> str:
    src = rel["source"]
    check = ("SHA-256 verified against the run's `publish.json`" if verified else
             "No `publish.json` in this run (published before sbom-publish); the "
             f"'{CONSOLIDATE_JOB}' job conclusion was checked instead")
    return "\n".join([
        f"Publishes the {product} {rel['version']} build {rel['build']} SBOM.",
        "",
        "| | |",
        "|---|---|",
        f"| Source run | {src['run_url']} |",
        f"| Xray build | `{src['build_name']}` / `{src['build_number']}` |",
        f"| Commit | `{src.get('commit') or 'n/a'}` |",
        f"| Generated | {rel['date']} |",
        f"| Components | {rel['components']:,} |",
        f"| CycloneDX | `{rel['zip']['path']}` ({site_render.human_size(rel['zip']['size'])}) |",
        f"| PDF | `{rel['pdf']['path']}` ({site_render.human_size(rel['pdf']['size'])}) |",
        f"| ZIP sha256 | `{rel['zip']['sha256']}` |",
        f"| PDF sha256 | `{rel['pdf']['sha256']}` |",
        f"| SBOM (.cdx.json) sha256 | `{src['sbom_sha256']}` |",
        "",
        check + ".",
        "",
        "Review the rendered row in `index.html` before merging: these reports are "
        "published as legal license declarations.",
    ])


def _write_outputs(values: dict) -> None:
    for key, value in values.items():
        if "\n" in str(value) or "\r" in str(value):
            raise ValueError(f"output {key} contains a line break")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--run", required=True, help="run ID or run URL")
    p.add_argument("--project")
    p.add_argument("--version")
    p.add_argument("--build")
    p.add_argument("--replace", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--pr-body-out", default="pr-body.md")
    o = sub.add_parser("open-pr")
    o.add_argument("--branch", required=True)
    o.add_argument("--title", required=True)
    o.add_argument("--body-file", required=True)
    o.add_argument("--base", default="main")
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN")
    if not token:
        print("[ERROR] GH_TOKEN is not set", file=sys.stderr)
        return 1
    gh = GitHub(token)
    try:
        if args.command == "prepare":
            result = prepare(gh, parse_run_id(args.run), project=args.project or None,
                             version=args.version or None, build=args.build or None,
                             replace=args.replace, dry_run=args.dry_run)
            body = pr_body(result["release"], result["product"], result["verified"])
            Path(args.pr_body_out).write_text(body + "\n", encoding="utf-8")
            _write_outputs({"branch": result["branch"], "title": result["title"]})
            _summary(f"## {result['title']}{' (dry run)' if args.dry_run else ''}\n\n{body}")
            print(body)
        else:
            repo = os.environ["GITHUB_REPOSITORY"]
            pr = gh.post_json(f"/repos/{repo}/pulls", {
                "title": args.title, "head": args.branch, "base": args.base,
                "body": Path(args.body_file).read_text(encoding="utf-8"),
            })
            _summary(f"Opened {pr['html_url']}")
            print(pr["html_url"])
    except urllib.error.HTTPError as exc:
        print(f"[ERROR] GitHub API {exc.code} for {exc.url}: {exc.read()[:500]!r}",
              file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
