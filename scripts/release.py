#!/usr/bin/env python3
"""Synchronise et publie les assets d'une release morfPackages.

Les binaires ne passent jamais par Git. Cette commande ne les lit et ne les
écrit qu'au travers de ``gh release`` ; Git sert uniquement au préflight du
petit dépôt qui porte le contrat durable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ReleaseError(RuntimeError):
    """A deliberate refusal: continuing could publish an ambiguous artifact."""


def run(command: list[str], *, capture: bool = False) -> str:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=HERE, text=True, capture_output=capture)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseError(detail or f"command failed ({result.returncode})")
    return result.stdout if capture else ""


def repository() -> str:
    url = run(["git", "remote", "get-url", "origin"], capture=True).strip()
    match = re.search(r"github\.com[:/]([^/]+/[^/.]+)(?:\.git)?$", url)
    if not match:
        raise ReleaseError(f"origin is not a GitHub repository: {url}")
    return match.group(1)


def preflight() -> None:
    """Refuse a local Git state which cannot be fast-forwarded safely."""
    run(["git", "fetch", "--prune"])
    if run(["git", "status", "--porcelain"], capture=True).strip():
        raise ReleaseError("working tree is dirty; resolve it before publishing")
    try:
        counts = run(["git", "rev-list", "--left-right", "--count",
                      "@{upstream}...HEAD"], capture=True).split()
    except ReleaseError as exc:
        raise ReleaseError("branch has no usable upstream; cannot preflight") from exc
    if len(counts) != 2 or counts[1] != "0":
        raise ReleaseError("local branch is ahead of or diverges from its upstream")
    run(["git", "pull", "--ff-only"])


def release_name(project: str, version: str) -> str:
    return f"{project.lower()}-v{version}"


def source_repository(distribution_repo: str, project: str) -> str:
    """Find the matching source remote in this same workspace.

    The distribution repository name carries the workspace suffix when there is
    one. Keeping that suffix instead of spelling it here makes sandbox releases
    target private source repositories while production targets canonical ones.
    """
    owner, package_name = distribution_repo.split("/", 1)
    marker = "morfPackages"
    suffix = package_name[len(marker):] if package_name.startswith(marker) else ""
    return f"{owner}/{project}{suffix}"


def ensure_source_release(distribution_repo: str, project: str, version: str) -> tuple[str, str]:
    """Require the authoritative release and its exact conventional source tag."""
    source = source_repository(distribution_repo, project)
    tag = f"v{version}"
    result = subprocess.run(["gh", "release", "view", tag, "--repo", source,
                             "--json", "tagName"],
                            cwd=HERE, text=True, capture_output=True)
    if result.returncode:
        raise ReleaseError(f"source release missing: {source} tag {tag}")
    try:
        release_tag = json.loads(result.stdout).get("tagName")
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"source release cannot be read: {source} tag {tag}") from exc
    if release_tag != tag:
        raise ReleaseError(f"source release is not associated with tag {tag}: {source}")
    return source, tag


def source_tag_commit(source: str, tag: str) -> str:
    """Resolve an annotated or lightweight remote tag to its full commit SHA."""
    try:
        ref = json.loads(run(["gh", "api", f"repos/{source}/git/ref/tags/{tag}"],
                             capture=True))
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"source tag cannot be decoded: {source} {tag}") from exc
    target = ref.get("object")
    while isinstance(target, dict) and target.get("type") == "tag":
        sha = str(target.get("sha", ""))
        if not COMMIT.fullmatch(sha):
            raise ReleaseError(f"source tag has no complete SHA: {source} {tag}")
        try:
            annotated = json.loads(run(["gh", "api", f"repos/{source}/git/tags/{sha}"],
                                       capture=True))
        except json.JSONDecodeError as exc:
            raise ReleaseError(f"annotated source tag cannot be decoded: {source} {tag}") from exc
        target = annotated.get("object")
    if not isinstance(target, dict) or target.get("type") != "commit":
        raise ReleaseError(f"source tag does not resolve to a commit: {source} {tag}")
    commit = str(target.get("sha", ""))
    if not COMMIT.fullmatch(commit):
        raise ReleaseError(f"source tag has no complete commit SHA: {source} {tag}")
    return commit


def download_manifest(repo: str, name: str) -> dict | None:
    with tempfile.TemporaryDirectory(prefix="morfpackages-") as raw:
        target = Path(raw)
        result = subprocess.run(["gh", "release", "download", name, "--repo", repo,
                                 "--pattern", "manifest.json", "--dir", str(target),
                                 "--clobber"], cwd=HERE, text=True, capture_output=True)
        if result.returncode:
            view = subprocess.run(["gh", "release", "view", name, "--repo", repo],
                                  cwd=HERE, text=True, capture_output=True)
            if view.returncode:
                return None
            raise ReleaseError("existing release has no readable manifest.json")
        try:
            return json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseError("existing manifest.json is invalid") from exc


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_metadata(path: Path, project: str, version: str) -> tuple[Path, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid metadata: {path}") from exc
    artifact = path.parent / str(data.get("name", ""))
    required = ("name", "sha256", "commit", "target", "platform", "format", "dirty")
    missing = [key for key in required if key not in data]
    if missing or data.get("project") != project or data.get("version") != version:
        raise ReleaseError(f"metadata does not describe {project} {version}: {path}")
    if data["dirty"] is not False or not COMMIT.fullmatch(str(data["commit"])):
        raise ReleaseError(f"metadata provenance is not clean and complete: {path}")
    if not artifact.is_file() or artifact.name != data["name"]:
        raise ReleaseError(f"artifact missing beside metadata: {artifact}")
    platform = data["platform"]
    if not isinstance(platform, dict) or not platform.get("os") or not platform.get("arch"):
        raise ReleaseError(f"metadata platform is incomplete: {path}")
    actual_sha256 = checksum(artifact)
    if not SHA256.fullmatch(str(data["sha256"])) or data["sha256"] != actual_sha256:
        raise ReleaseError(f"artifact SHA-256 does not match metadata: {artifact}")
    data["sha256"] = actual_sha256
    return artifact, {key: data[key] for key in
                      ("name", "sha256", "commit", "target", "platform", "format")}


def write_manifest(folder: Path, project: str, version: str, entries: list[dict],
                   source: str, tag: str, commit: str) -> tuple[Path, Path]:
    entries.sort(key=lambda item: item["name"])
    manifest = {"schema_version": SCHEMA_VERSION, "project": project,
                "version": version,
                "source": {"repository": source, "tag": tag, "commit": commit},
                "artifacts": entries}
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    checksums = folder / "checksums.sha256"
    checksums.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in entries),
                         encoding="utf-8")
    return manifest_path, checksums


def publish(args: argparse.Namespace) -> int:
    preflight()
    repo = repository()
    source, tag = ensure_source_release(repo, args.project, args.version)
    tagged_commit = source_tag_commit(source, tag)

    candidates = [read_metadata(meta_path.resolve(), args.project, args.version)
                  for meta_path in args.metadata]
    for artifact, entry in candidates:
        if entry["commit"] != tagged_commit:
            raise ReleaseError(
                f"{args.project} {args.version}: artifact commit does not match source tag {tag}.\n"
                f"Artifact: {entry['commit']} ({artifact.name})\n"
                f"Tag:      {tagged_commit}\n"
                "No asset has been published."
            )

    name = release_name(args.project, args.version)
    old = download_manifest(repo, name)
    if old and (old.get("schema_version") != SCHEMA_VERSION or old.get("project") != args.project
                or old.get("version") != args.version):
        raise ReleaseError("existing release manifest identifies a different project or version")
    if old:
        recorded_source = old.get("source")
        if recorded_source and recorded_source != {
                "repository": source, "tag": tag, "commit": tagged_commit}:
            raise ReleaseError("existing release records a different authoritative source")
        for entry in old.get("artifacts", []):
            if entry.get("commit") != tagged_commit:
                raise ReleaseError(
                    f"existing release contains an artifact from a different commit: "
                    f"{entry.get('name', '(unnamed)')}\n"
                    "No asset has been published."
                )
    existing = {entry["name"]: entry for entry in (old or {}).get("artifacts", [])}
    additions: list[tuple[Path, dict]] = []
    for artifact, entry in candidates:
        previous = existing.get(entry["name"])
        if previous == entry:
            print(f"already published: {entry['name']}")
            continue
        if previous:
            raise ReleaseError(f"conflict for {entry['name']}: commit or checksum differs")
        existing[entry["name"]] = entry
        additions.append((artifact, entry))
    if not additions:
        print("nothing to publish")
        return 0
    if old is None:
        run(["gh", "release", "create", name, "--repo", repo,
             "--title", f"{args.project} - v{args.version}",
             "--notes", args.notes or f"Distribution artifacts for {args.project} {args.version}."])
    upload = ["gh", "release", "upload", name, "--repo", repo]
    run(upload + [str(path) for path, _ in additions])
    with tempfile.TemporaryDirectory(prefix="morfpackages-") as raw:
        manifest, checksums = write_manifest(Path(raw), args.project, args.version,
                                             list(existing.values()), source, tag, tagged_commit)
        run(["gh", "release", "upload", name, "--repo", repo, "--clobber",
             str(manifest), str(checksums)])
    print(f"published {len(additions)} artifact(s) to {repo} release {name}")
    return 0


def sync(args: argparse.Namespace) -> int:
    repo = repository()
    name = release_name(args.project, args.version)
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["gh", "release", "view", name, "--repo", repo,
                             "--json", "assets", "--jq", ".assets[].name"],
                            cwd=HERE, text=True, capture_output=True)
    if result.returncode:
        print(f"no published release to sync: {name}")
        return 0
    assets = [line for line in result.stdout.splitlines()
              if line not in ("manifest.json", "checksums.sha256")]
    for asset in assets:
        run(["gh", "release", "download", name, "--repo", repo, "--pattern", asset,
             "--dir", str(output), "--clobber"])
    print(f"synced {len(assets)} artifact(s) from {name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage morfPackages GitHub Release assets.")
    commands = parser.add_subparsers(dest="command", required=True)
    publish_parser = commands.add_parser("publish", help="validate and upload artifact sidecars")
    publish_parser.add_argument("--project", required=True)
    publish_parser.add_argument("--version", required=True)
    publish_parser.add_argument("--metadata", type=Path, action="append", required=True)
    publish_parser.add_argument("--notes", help="release text used only when creating the release")
    sync_parser = commands.add_parser("sync", help="download existing artifact assets")
    sync_parser.add_argument("--project", required=True)
    sync_parser.add_argument("--version", required=True)
    sync_parser.add_argument("--out", type=Path, required=True)
    commands.add_parser("preflight", help="verify and fast-forward this repository")
    args = parser.parse_args()
    try:
        if args.command == "publish":
            return publish(args)
        if args.command == "sync":
            return sync(args)
        preflight()
        print("morfPackages repository is ready")
        return 0
    except ReleaseError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
