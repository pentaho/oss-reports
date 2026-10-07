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
| `index.html`, `assets/css/site.css` | The GitHub Pages site (static HTML, no Jekyll build -- see `.nojekyll`) |
| `pentaho-suite/` | Pentaho Data Integration and Analytics |
| `openlineage-plugin/` | Pentaho Data Lineage Plugin |
| `pentaho-catalog/` | Pentaho Data Catalog |
| `archive/` | Legacy reports (PDF, TXT, ZIP) published before the CycloneDX format |
| `manifest.yml` | Maps pdia-security build names to product folders for automated publishing |

## Publishing a release

1. Download the `sbom-<build>-<n>` and `sbom-pdf-<build>-<n>` artifacts from the `SBOM Consolidation` run in [pentaho/pdia-security](https://github.com/pentaho/pdia-security), or render the PDF from an existing SBOM with `.github/scripts/cyclonedx-to-pdf/cyclonedx_to_pdf.py` from that repo.
2. Zip the `.cdx.json` as `sbom-{build-name}-{version}.zip` and copy it with the `.pdf` into the product folder from `manifest.yml`.
3. In `index.html`, add a table row directly after the product's `<!-- project:{key} -->` marker (newest first), copying an existing row and updating the version, build, generation date, component count, links and file sizes. Move the `Latest` badge if the release supersedes the previous one on the same release line, and update the release count in the hero.

Preview locally with `python3 -m http.server` from the repository root.

<sub>Copyright 2026 Pentaho. All rights reserved. Licensed under [Apache 2.0](LICENSE).</sub>
