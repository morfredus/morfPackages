# morfPackages

[![Version](https://img.shields.io/badge/version-0.4.0-blue)](CHANGELOG.md)

`morfPackages` publishes the installable morfSystem artifacts without taking ownership of their source builds. The Git repository deliberately contains only the release contract and the scripts that enforce it; every binary lives only as a GitHub Release asset.

Each release is named `<project>-v<version>`. It gathers the artifacts built for that version on every supported platform, plus `manifest.json` and `checksums.sha256`. The manifest is the durable, machine-readable record of the full source commit, target and SHA-256 for each artifact.

The source project remains authoritative. Before accepting an artifact, the publishing script verifies that its public source repository already has a release for the same version. It never builds a project, changes a source release, or replaces an asset silently.

## Workflow

Run the scripts from a clean checkout. `scripts/publish-release.py` starts with a Git preflight, validates the public source release, detects conflicts through the manifest, then uploads only the missing artifacts. `scripts/sync-release-assets.py` retrieves assets already published for a project release into a common distribution directory. Both use `gh release` exclusively for release assets.

The machine that built an artifact supplies a small JSON sidecar with the artifact name, SHA-256, full commit, target and platform. The sidecar is validated and becomes the matching manifest entry; it is not uploaded as a release asset.

See [schema/manifest.schema.json](schema/manifest.schema.json) for the v1 contract.
