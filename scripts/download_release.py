"""
Download the latest pfReporting wheel from Azure DevOps pipeline artifacts.

The script resolves the pipeline by name, finds the latest successful run,
downloads the named artifact, and extracts any .whl files into downloads/release/.

Usage:
    python scripts/download_release.py --organization <org> --project <project>

Environment variables:
    AZURE_DEVOPS_ORG       Azure DevOps organization name
    AZURE_DEVOPS_PROJECT   Azure DevOps project name
    AZURE_DEVOPS_PAT       Personal Access Token with build read access

Optional arguments:
    --pipeline-name        Azure DevOps pipeline name or YAML pipeline name
    --artifact-name        Artifact name published by the pipeline
    --run-id               Download a specific pipeline run instead of the latest one
    --output-dir           Directory where the wheel should be extracted
    --keep-archive         Keep the downloaded artifact archive on disk
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


API_VERSION = "7.1"
DEFAULT_PIPELINE_NAME = "pfReporting wheel build"
DEFAULT_ARTIFACT_NAME = "pfreporting-wheel"
DEFAULT_OUTPUT_DIR = Path("downloads") / "release"


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return context


SSL_CONTEXT = build_ssl_context()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the latest successful pfReporting wheel from Azure DevOps.",
    )
    parser.add_argument(
        "--organization",
        default=os.environ.get("AZURE_DEVOPS_ORG"),
        help="Azure DevOps organization name (or AZURE_DEVOPS_ORG).",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("AZURE_DEVOPS_PROJECT"),
        help="Azure DevOps project name (or AZURE_DEVOPS_PROJECT).",
    )
    parser.add_argument(
        "--pipeline-name",
        default=DEFAULT_PIPELINE_NAME,
        help=f"Pipeline name to query (default: {DEFAULT_PIPELINE_NAME!r}).",
    )
    parser.add_argument(
        "--artifact-name",
        default=DEFAULT_ARTIFACT_NAME,
        help=f"Artifact name to download (default: {DEFAULT_ARTIFACT_NAME!r}).",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Specific pipeline run to download. If omitted, the latest successful run is used.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for extracted wheel files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded artifact zip alongside the extracted wheel.",
    )
    return parser.parse_args()


def read_pat() -> str:
    pat = os.environ.get("AZURE_DEVOPS_PAT") or os.environ.get("SYSTEM_ACCESSTOKEN")
    if not pat:
        raise SystemExit(
            "Missing Azure DevOps token. Set AZURE_DEVOPS_PAT or SYSTEM_ACCESSTOKEN."
        )
    return pat


def auth_header(pat: str) -> dict[str, str]:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def request_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} while requesting {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to request {url}: {exc.reason}") from exc


def download_file(url: str, headers: dict[str, str], destination: Path) -> None:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
            destination.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} while downloading {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download {url}: {exc.reason}") from exc


def resolve_pipeline_id(
    base_url: str,
    headers: dict[str, str],
    pipeline_name: str,
) -> int:
    url = f"{base_url}/_apis/pipelines?name={urllib.parse.quote(pipeline_name)}&api-version={API_VERSION}"
    payload = request_json(url, headers)
    pipelines = payload.get("value", [])
    if not pipelines:
        raise SystemExit(f"No pipeline found with name {pipeline_name!r}.")

    for pipeline in pipelines:
        if pipeline.get("name") == pipeline_name:
            return int(pipeline["id"])

    return int(pipelines[0]["id"])


def resolve_run_id(
    base_url: str,
    headers: dict[str, str],
    pipeline_id: int,
    explicit_run_id: int | None,
) -> int:
    if explicit_run_id is not None:
        return explicit_run_id

    url = f"{base_url}/_apis/pipelines/{pipeline_id}/runs?api-version={API_VERSION}&$top=20"
    payload = request_json(url, headers)
    runs = payload.get("value", [])
    if not runs:
        raise SystemExit(f"No pipeline runs found for pipeline id {pipeline_id}.")

    for run in runs:
        if str(run.get("state", "")).lower() != "completed":
            continue
        if str(run.get("result", "")).lower() == "succeeded":
            return int(run["id"])

    raise SystemExit(f"No successful pipeline run found for pipeline id {pipeline_id}.")


def resolve_artifact_url(
    base_url: str,
    headers: dict[str, str],
    pipeline_id: int,
    run_id: int,
    artifact_name: str,
) -> str:
    url = (
        f"{base_url}/_apis/pipelines/{pipeline_id}/runs/{run_id}/artifacts"
        f"?api-version={API_VERSION}"
    )
    payload = request_json(url, headers)
    artifacts = payload.get("value", [])
    for artifact in artifacts:
        if artifact.get("name") != artifact_name:
            continue
        resource = artifact.get("resource", {})
        download_url = resource.get("downloadUrl")
        if download_url:
            return str(download_url)
    available = ", ".join(sorted(str(item.get("name")) for item in artifacts)) or "<none>"
    raise SystemExit(
        f"Artifact {artifact_name!r} not found for run {run_id}. Available artifacts: {available}"
    )


def extract_wheels(archive_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if not member.endswith(".whl"):
                continue
            target = output_dir / Path(member).name
            with archive.open(member) as source, target.open("wb") as dest:
                dest.write(source.read())
            extracted.append(target)

    if not extracted:
        raise SystemExit(f"No wheel file found inside archive {archive_path}.")
    return extracted


def main() -> int:
    args = parse_args()
    if not args.organization or not args.project:
        raise SystemExit(
            "Missing Azure DevOps organization/project. Pass --organization and --project, "
            "or set AZURE_DEVOPS_ORG and AZURE_DEVOPS_PROJECT."
        )

    pat = read_pat()
    headers = auth_header(pat)
    base_url = f"https://dev.azure.com/{args.organization}/{args.project}"

    pipeline_id = resolve_pipeline_id(base_url, headers, args.pipeline_name)
    run_id = resolve_run_id(base_url, headers, pipeline_id, args.run_id)
    artifact_url = resolve_artifact_url(
        base_url,
        headers,
        pipeline_id,
        run_id,
        args.artifact_name,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = args.output_dir / f"{args.artifact_name}-run-{run_id}.zip"

    print(f"Pipeline id: {pipeline_id}")
    print(f"Run id: {run_id}")
    print(f"Artifact: {args.artifact_name}")
    print(f"Downloading: {artifact_url}")
    print(f"Archive: {archive_path}")

    download_file(artifact_url, headers, archive_path)
    wheels = extract_wheels(archive_path, args.output_dir)

    if not args.keep_archive:
        archive_path.unlink(missing_ok=True)

    print("Downloaded wheel(s):")
    for wheel in wheels:
        print(f" - {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())