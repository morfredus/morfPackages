# morfPackages

[![Version](https://img.shields.io/badge/version-0.6.1-blue)](CHANGELOG.md)

`morfPackages` publishes the installable morfSystem artifacts without taking ownership of their source builds. The Git repository deliberately contains only the release contract and the scripts that enforce it; every binary lives only as a GitHub Release asset.

Each release is named `<project>-v<version>`. It gathers the artifacts built for that version on every supported platform, plus `manifest.json` and `checksums.sha256`. The manifest records the authoritative source repository, tag and full commit, alongside each artifact's target and SHA-256.

The source project remains authoritative. Before accepting an artifact, the publishing script resolves the source repository for the current workspace, verifies its `vX.Y.Z` release and remote tag, then requires its full commit SHA to match the artifact provenance. It never builds a project or replaces an asset silently. Once checked, the same artifacts, manifest and checksums are mirrored to the source release so users can download them from the project release page.

## Workflow

Run the scripts from a clean checkout. `scripts/release.py publish` starts with a Git preflight, validates the public source release, detects conflicts through the manifest, then uploads only the missing artifacts and mirrors them to the source release. `scripts/release.py sync` retrieves assets already published for a project release into a common distribution directory. Both use `gh release` exclusively for release assets.

The machine that built an artifact supplies a small JSON sidecar with the artifact name, SHA-256, full commit, target and platform. The sidecar is validated and becomes the matching manifest entry; it is not uploaded as a release asset.

If a local reconstruction has the same name as an indexed asset but differs in
commit or checksum, the indexed asset remains immutable. It is still mirrored
to the source release when that release does not contain it yet.

See [schema/manifest.schema.json](schema/manifest.schema.json) for the v1 contract.
