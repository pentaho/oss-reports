# Pentaho Open Source Reports

Software Bill of Materials (SBOM) for Pentaho products, listing all open-source components, their versions, and licenses.

Reports are published in [CycloneDX](https://cyclonedx.org/) format -- the industry standard for machine-readable SBOMs. Each report is a `.zip` archive containing a CycloneDX JSON file with full license texts and evidence.

---

## Current Reports

<!-- project:pdia -->
### Pentaho Data Integration and Analytics

The full Pentaho platform suite.

| Version | Format | Download |
|---|---|---|
| *Coming soon* | CycloneDX | -- |
<!-- /project:pdia -->

<!-- project:pdi-openlineage-plugin-ee -->
### Pentaho Data Lineage Plugin

OpenLineage integration plugin for Pentaho Data Integration.

| Version | Format | Download |
|---|---|---|
| 0.7.0-292 | CycloneDX | [sbom-pdi-openlineage-plugin-ee-main-0.7.0-292.zip](openlineage-plugin/sbom-pdi-openlineage-plugin-ee-main-0.7.0-292.zip) |
<!-- /project:pdi-openlineage-plugin-ee -->

<!-- project:pdc-docker-deployment -->
### Pentaho Data Catalog

| Version | Format | Download |
|---|---|---|
| *Coming soon* | CycloneDX | -- |
<!-- /project:pdc-docker-deployment -->

---

## File Naming Convention

All SBOM files follow this pattern:

```
sbom-{build-name}-{version}.zip
```

- **build-name** - the CI build identifier (e.g. `pdi-openlineage-plugin-ee-main`)
- **version** - the release version and build number (e.g. `0.7.0-292`)

This convention enables automated publishing from CI pipelines.

---

## About the Format

Reports use [CycloneDX 1.6](https://cyclonedx.org/specification/overview/) JSON format and include:

- Complete component inventory with PURLs ([Package URLs](https://github.com/package-url/purl-spec))
- SPDX license identifiers with full license texts
- License evidence and concluded (most-permissive) license per component
- Snippet-scanned JavaScript libraries with copyright headers
- SHA-256 hashes for integrity verification

Tools to view CycloneDX SBOMs: [CycloneDX CLI](https://github.com/CycloneDX/cyclonedx-cli), [Dependency-Track](https://dependencytrack.org/), or any JSON viewer.

---

<details>
<summary>Archive - Legacy Reports (pre-CycloneDX)</summary>

<div class="archive-content" markdown="1">

These reports were generated in older formats (PDF, TXT, ZIP) and are retained for reference.

### Pentaho Data Integration and Analytics

| Version | Download |
|---|---|
| 11.0.0.0 | [Pentaho_Suite-11.0.0.0.zip](archive/pentaho-suite/Pentaho_Suite-11.0.0.0.zip) |
| 10.2.0.3 | [PentahoSuite_OSS_Licenses_v10.2.0.3.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v10.2.0.3.pdf) |
| 10.2.0.2 | [PentahoSuite_OSS_Licenses_v10.2.0.2.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v10.2.0.2.pdf) |
| 10.2.0.0 | [PentahoSuite_OSS_Licenses_v10.2.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v10.2.0.0.pdf) |
| 10.1.0.0 | [PentahoSuite_OSS_Licenses_v10.1.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v10.1.0.0.pdf) |
| 10.0.0.0 | [PentahoSuite_OSS_Licenses_v10.0.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v10.0.0.0.pdf) |
| 9.4.0.0 | [PentahoSuite_OSS_Licenses_v9.4.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v9.4.0.0.pdf) |
| 9.3.0.0 | [PentahoSuite_OSS_Licenses_v9.3.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v9.3.0.0.pdf) |
| 9.2.0.3 | [PentahoSuite_OSS_Licenses_v9.2.0.3.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v9.2.0.3.pdf) |
| 9.2.0.0 | [PentahoSuite_OSS_Licenses_v9.2.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v9.2.0.0.pdf) |
| 9.1.0.0 | [PentahoSuite_OSS_Licenses_v9.1.0.0.pdf](archive/pentaho-suite/PentahoSuite_OSS_Licenses_v9.1.0.0.pdf) |

### Pentaho Data Lineage Plugin

| Version | Download |
|---|---|
| 10.2.1.0 | [PDIOpenLineagePlugin_OSS_Licenses_v10.2.1.0.pdf](archive/openlineage-plugin/PDIOpenLineagePlugin_OSS_Licenses_v10.2.1.0.pdf) |
| 0.6.0 | [Open_Lineage_BoM_license_attribution_report-0.6.0-213.txt](archive/openlineage-plugin/Open_Lineage_BoM_license_attribution_report-0.6.0-213.txt) |
| 0.5.0 | [Open_Lineage_BoM_license_attribution_report-0.5.0-184.txt](archive/openlineage-plugin/Open_Lineage_BoM_license_attribution_report-0.5.0-184.txt) |
| 0.4.0 | [Open_Lineage-0.4.0-116.txt](archive/openlineage-plugin/Open_Lineage-0.4.0-116.txt) |
| 0.3.0 | [Open_Lineage_BoM_license_attribution_report-0.3.0-1629.txt](archive/openlineage-plugin/Open_Lineage_BoM_license_attribution_report-0.3.0-1629.txt) |
| 0.2.0 | [PDI-OpenLineage-Plugin_OSS_Licenses_V0.2.0.pdf](archive/openlineage-plugin/PDI-OpenLineage-Plugin_OSS_Licenses_V0.2.0.pdf) |

### Pentaho Data Catalog

| Version | Download |
|---|---|
| 10.2 | [Pentaho_Data_Catalog_OSS_Licenses_V10.2.pdf](archive/pentaho-catalog/Pentaho_Data_Catalog_OSS_Licenses_V10.2.pdf) |

</div>
</details>

---

<sub>Copyright 2025 Pentaho. All rights reserved. Licensed under [Apache 2.0](LICENSE).</sub>
