# Pentaho Open Source Reports

Software Bill of Materials (SBOM) for Pentaho products, listing all open-source components, their versions, and licenses.

**Browse and download the reports at <https://pentaho.github.io/oss-reports/>.**

Each release is published in two formats, side by side:

| Format | File | Purpose |
|---|---|---|
| [CycloneDX 1.6](https://cyclonedx.org/specification/overview/) JSON | `sbom-{build-name}-{version}.zip` | Machine-readable, authoritative SBOM with PURLs, SPDX license ids, full license texts, evidence and SHA-256 hashes |
| PDF report | `sbom-{build-name}-{version}.pdf` | Human-readable rendering of the same SBOM: a components table, then one section per license with its full text and the covered components with their copyright |

## Repository layout

| Path | Contents |
|---|---|
| `index.html`, `assets/` | The GitHub Pages site (static HTML, CSS and a small copy-to-clipboard script). Only these files and `LICENSE` are deployed, by `.github/workflows/pages.yml` |
| `pentaho-suite/` | Pentaho Data Integration and Analytics |
| `pentaho-containers/` | Pentaho Container Images (`pdi` and `pentaho-server` Docker images) |
| `openlineage-plugin/` | Pentaho Data Lineage Plugin |
| `pentaho-catalog/` | Pentaho Data Catalog |
| `archive/` | Legacy reports (PDF, TXT, ZIP) published before the CycloneDX format |
| `releases.json` | Source of truth for every CycloneDX release: product, version, build, date, component count, files with size and SHA-256, plus the source pdia-security run for automated publishes |
| `manifest.yml` | Product configuration: folder, build-name routing and version rules for automated publishing |
| `.github/workflows/publish-sbom.yml` | Publishes a pdia-security run as a pull request |
| `.github/workflows/pages.yml` | Deploys the site on every push to `main` (requires Settings -> Pages -> Source: GitHub Actions) |
| `.github/scripts/publish/` | `publish.py` (fetch, verify, write files, update `releases.json`), `site_render.py` (render `index.html` from `releases.json`) and their tests |

## Hosting

The report files stay committed in this repository (versioned, protected `main` branch) but are not part of the deployed site: every download link points to `https://raw.githubusercontent.com/pentaho/oss-reports/main/<path>`, which serves them as downloads. This keeps the published site far below the GitHub Pages 1 GB limit. Each row's shield icon opens the SHA-256 of its ZIP and PDF (recorded in `releases.json`, checked by the tests) with copy buttons.

## Publishing a release

Run the **Publish SBOM** workflow (Actions -> Publish SBOM -> Run workflow) with the ID **or URL** of a `SBOM Consolidation` or `Xray Build` run in [pentaho/pdia-security](https://github.com/pentaho/pdia-security). It:

1. checks the run is from one of those two workflows and has completed;
2. reads the run's `sbom-publish-*` artifact (`publish.json`), which only exists when consolidation succeeded, and verifies the SBOM and PDF against its SHA-256. Runs from before that artifact existed fall back to checking the `Consolidate SBOM` job and the run title;
3. routes the build to a product and derives the displayed version and build from `manifest.yml`;
4. writes `{folder}/sbom-{safe-build-name}-{build-number}.zip` (the zipped `.cdx.json`) and `.pdf`, records their size and SHA-256 in `releases.json` and re-renders `index.html`;
5. opens a pull request with the source run, build, component count, sizes and hashes for review.

| Input | Use |
|---|---|
| `run` | Run ID or URL (required) |
| `dry_run` | Report what would be published in the job summary, change nothing |
| `replace` | Re-publish a build that is already on the site |
| `project`, `version`, `build` | Override the routing or the displayed version/build when `manifest.yml` gets it wrong (version/build: letters, digits, `.`, `_`, `+`, `-`) |

The workflow uses the `SECURITYSCAN_GITHUB_API_KEY` secret (actions read on pdia-security, contents and pull requests write here).

### Editing the site by hand

Never edit the release rows of `index.html` directly: edit `releases.json` and run `python3 .github/scripts/publish/site_render.py`. Rows are ordered newest first and the `Latest` badge marks the newest release of each release line (first two version segments); the hero counts are recomputed. The `Tests` workflow fails a pull request whose `index.html` does not match `releases.json`. Everything outside the `<!-- project:{key} -->` markers and the hero counts is plain hand-maintained HTML.

### Tests

```bash
pip install -r .github/scripts/publish/requirements.txt
python3 -m unittest discover -s .github/scripts/publish/tests -v
python3 .github/scripts/publish/site_render.py --check
```

Preview locally with `python3 -m http.server` from the repository root (download links resolve to `main` on GitHub).

<sub>Copyright 2026 Pentaho. All rights reserved. Licensed under the [Business Source License 1.1](LICENSE).</sub>
