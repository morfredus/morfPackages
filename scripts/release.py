#!/usr/bin/env python3
"""Synchronise et publie les assets des releases de distribution et source.

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
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ReleaseError(RuntimeError):
    """A deliberate refusal: continuing could publish an ambiguous artifact."""


# Erreurs SERVEUR transitoires de GitHub : gh les fait remonter en clair
# ("HTTP 502: Server Error", "HTTP 429", "timeout"...). Elles ne disent rien sur
# la validite de la demande, juste que l'API a hoquete. Un seul de ces hoquets
# faisait echouer toute la publication du parc (vu sur un upload de manifest.json
# rendu en 502) : on reessaie donc au lieu d'abandonner.
_TRANSIENT = re.compile(
    r"HTTP (5\d\d|429)|Server Error|Bad Gateway|Service Unavailable|"
    r"Gateway Time-?out|timeout|timed out|connection reset|\bEOF\b|too quickly",
    re.IGNORECASE)


def _transient(text: str) -> bool:
    return bool(_TRANSIENT.search(text or ""))


def _attempt(command: list[str], *, retries: int = 4) -> subprocess.CompletedProcess:
    """Lance une commande en ne reessayant QUE les hoquets serveur de GitHub.

    Capture toujours les deux flux, pour pouvoir lire le signal transitoire ;
    l'appelant reste libre de traiter un code non nul comme fatal (sonde
    d'existence) ou de le laisser remonter. Seul ``gh`` est reessaye : un echec
    de ``git`` n'est jamais un hoquet serveur ici.
    """
    result = subprocess.run(command, cwd=HERE, text=True, capture_output=True)
    for attempt in range(1, retries):
        if result.returncode == 0 or command[:1] != ["gh"]:
            return result
        if not _transient((result.stderr or "") + (result.stdout or "")):
            return result
        wait = 2.0 * attempt
        print(f"  GitHub a renvoye une erreur transitoire ; nouvel essai dans "
              f"{wait:.0f} s ({attempt}/{retries - 1})...", file=sys.stderr)
        time.sleep(wait)
        result = subprocess.run(command, cwd=HERE, text=True, capture_output=True)
    return result


def run(command: list[str], *, capture: bool = False) -> str:
    print("$ " + " ".join(command))
    result = _attempt(command)
    if not capture:
        # _attempt capture toujours (pour lire le signal transitoire) ; on
        # re-emet la sortie pour garder l'affichage d'avant quand capture=False.
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
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
    result = _attempt(["gh", "release", "view", tag, "--repo", source,
                       "--json", "tagName"])
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
        result = _attempt(["gh", "release", "download", name, "--repo", repo,
                           "--pattern", "manifest.json", "--dir", str(target),
                           "--clobber"])
        if result.returncode:
            view = _attempt(["gh", "release", "view", name, "--repo", repo])
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


def release_asset_names(repo: str, name: str) -> set[str]:
    """Return the uploaded asset names of an existing GitHub release."""
    raw = run(["gh", "release", "view", name, "--repo", repo,
               "--json", "assets", "--jq", ".assets[].name"], capture=True)
    return {line.strip() for line in raw.splitlines() if line.strip()}


def edit_source_release_notes(source: str, tag: str, project: str, version: str,
                              notes: str) -> None:
    """Update title and body without sending tag_name.

    ``gh release edit`` includes tag_name in the PATCH. GitHub then answers
    422 ``Release.tag_name already exists`` when that tag already has a
    release. The zip can already be published; only the notes rewrite fails.
    ``gh release view --json id`` returns a GraphQL node id (RE_kwDO…), which
    REST refuses with 404. The releases/tags route returns the numeric id.
    """
    ident = run(["gh", "api", f"repos/{source}/releases/tags/{tag}",
                 "--jq", ".id"], capture=True).strip()
    run(["gh", "api", "--method", "PATCH", f"repos/{source}/releases/{ident}",
         "--raw-field", f"name={project} - v{version}",
         "--raw-field", f"body={notes}"])


def upload_control_assets(repo: str, release: str, *paths: Path) -> None:
    """Replace each evolving manifest asset in a separate GitHub request.

    GitHub CLI can reject one member of a multi-asset --clobber upload after it
    has already replaced another one. Separate requests keep retries harmless.

    ``--clobber`` (delete-then-upload) is not always honoured: GitHub sometimes
    answers 422 "already exists", typically when a previous attempt already
    uploaded the asset but returned a transient error to the client. Since a
    control asset is deterministic for a given version and set of artifacts, we
    make the upload idempotent: on "already exists" we delete the asset outright
    and upload it again, so our freshly generated content always wins.
    """
    for path in paths:
        try:
            run(["gh", "release", "upload", release, "--repo", repo, "--clobber", str(path)])
        except ReleaseError as exc:
            if "already exists" not in str(exc).lower():
                raise
            run(["gh", "release", "delete-asset", release, path.name, "--repo", repo, "--yes"])
            run(["gh", "release", "upload", release, "--repo", repo, str(path)])


def mirror_source_release(distribution_repo: str, distribution_name: str,
                          source: str, tag: str, project: str, version: str,
                          artifact_names: list[str], manifest: Path, checksums: Path,
                          notes: str | None) -> None:
    """Expose checked package assets on the release users visit first.

    morfPackages remains the canonical distribution index and retains the
    manifest validation.  The project release receives byte-identical copies so
    an end user does not need to discover a second repository to download an
    installable. Existing source assets are downloaded and hashed before being
    accepted: this never silently replaces an uploaded binary.
    """
    source_assets = release_asset_names(source, tag)
    with tempfile.TemporaryDirectory(prefix="morfpackages-source-") as raw:
        folder = Path(raw)
        files: list[Path] = []
        for asset_name in artifact_names:
            run(["gh", "release", "download", distribution_name, "--repo", distribution_repo,
                 "--pattern", asset_name, "--dir", str(folder), "--clobber"])
            local = folder / asset_name
            if not local.is_file():
                raise ReleaseError(f"distribution asset cannot be downloaded: {asset_name}")
            if asset_name in source_assets:
                checked = folder / "existing" / asset_name
                checked.parent.mkdir(parents=True, exist_ok=True)
                run(["gh", "release", "download", tag, "--repo", source,
                     "--pattern", asset_name, "--dir", str(checked.parent), "--clobber"])
                if not checked.is_file() or checksum(checked) != checksum(local):
                    raise ReleaseError(
                        f"source release already contains a different asset: {asset_name}")
            else:
                files.append(local)
        if files:
            run(["gh", "release", "upload", tag, "--repo", source,
                 *[str(path) for path in files]])
        # Unlike binaries, these files represent the complete current index.
        # They must evolve when a platform is added and are therefore replaced.
        upload_control_assets(source, tag, manifest, checksums)
        if notes:
            edit_source_release_notes(source, tag, project, version, notes)
    print(f"mirrored {len(files)} asset(s) to {source} release {tag}")


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
            # Un asset portant ce nom est déjà la référence immuable de cette
            # release. Le dossier dist peut contenir une reconstruction plus
            # récente, donc différente octet pour octet, du même tag source.
            # Ne jamais remplacer l'asset publié. Le manifeste existant a
            # déjà été vérifié contre le tag et peut être recopié sans risque
            # vers la release utilisateur qui lui manquerait encore.
            print(f"retaining indexed artifact: {entry['name']} "
                  "(local commit or checksum differs)")
            continue
        existing[entry["name"]] = entry
        additions.append((artifact, entry))
    if old is None:
        run(["gh", "release", "create", name, "--repo", repo,
             "--title", f"{args.project} - v{args.version}",
             "--notes", args.notes or f"Distribution artifacts for {args.project} {args.version}."])
    if additions:
        upload = ["gh", "release", "upload", name, "--repo", repo]
        run(upload + [str(path) for path, _ in additions])
    with tempfile.TemporaryDirectory(prefix="morfpackages-") as raw:
        manifest, checksums = write_manifest(Path(raw), args.project, args.version,
                                             list(existing.values()), source, tag, tagged_commit)
        upload_control_assets(repo, name, manifest, checksums)
        mirror_source_release(repo, name, source, tag, args.project, args.version,
                              sorted(existing), manifest, checksums, args.notes)
    print(f"published {len(additions)} artifact(s) to {repo} release {name}")
    return 0


def sync(args: argparse.Namespace) -> int:
    """Download indexed assets and derive matching local sidecars.

    ``dist`` is a cache shared between build hosts. An older local sidecar must
    never survive when its artifact is replaced by the immutable indexed copy.
    """
    repo = repository()
    name = release_name(args.project, args.version)
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = _attempt(["gh", "release", "view", name, "--repo", repo,
                       "--json", "assets", "--jq", ".assets[].name"])
    if result.returncode:
        print(f"no published release to sync: {name}")
        return 0
    manifest = download_manifest(repo, name)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseError(f"published release has no compatible manifest: {name}")
    if manifest.get("project") != args.project or manifest.get("version") != args.version:
        raise ReleaseError(f"published manifest identifies a different project or version: {name}")
    entries = {entry.get("name"): entry for entry in manifest.get("artifacts", [])
               if isinstance(entry, dict) and isinstance(entry.get("name"), str)}
    assets = [line for line in result.stdout.splitlines()
              if line not in ("manifest.json", "checksums.sha256")]
    for asset in assets:
        run(["gh", "release", "download", name, "--repo", repo, "--pattern", asset,
             "--dir", str(output), "--clobber"])
        entry = entries.get(asset)
        artifact = output / asset
        if not isinstance(entry, dict) or not artifact.is_file():
            raise ReleaseError(f"manifest has no matching artifact entry: {asset}")
        if entry.get("sha256") != checksum(artifact):
            raise ReleaseError(f"downloaded artifact checksum differs from manifest: {asset}")
        sidecar = {"project": args.project, "version": args.version,
                   "dirty": False, **entry}
        metadata = output / f"{asset}.metadata.json"
        metadata.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
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
