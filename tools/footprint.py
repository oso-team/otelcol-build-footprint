#!/usr/bin/env python3
"""Measure Collector build variants using public source and standard tools."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "experiment.json"
REPORT_NOTES = "Package reachability is measured from the resource-detection processor; binary size is for the complete stripped Collector."


class FootprintError(Exception):
    pass


def command(args: list[str], *, cwd: pathlib.Path | None = None,
            env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FootprintError(f"{' '.join(args[:2])} failed ({result.returncode}): {detail[-2000:]}")
    # OCB writes its version line to stderr even when the command succeeds.
    return result.stdout or result.stderr


def load_manifest(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise FootprintError("manifest schema_version must be 1")
    source = data.get("source", {})
    if not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")):
        raise FootprintError("source.commit must be a full 40-character Git SHA")
    if source.get("url") != "https://github.com/oso-team/opentelemetry-collector-contrib.git":
        raise FootprintError("this experiment requires the pinned public oso-team Contrib fork")
    if not data.get("builder", {}).get("components"):
        raise FootprintError("builder.components must name public Collector modules")
    targets = data.get("targets", [])
    if not targets or targets[0].get("id") != "full" or targets[0].get("tags") != []:
        raise FootprintError("the first target must be an untagged full baseline")
    ids = [target.get("id") for target in targets]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z0-9_-]+", str(i)) for i in ids):
        raise FootprintError("target IDs must be unique safe names")
    for target in targets:
        if not isinstance(target.get("tags"), list) or not all(
            re.fullmatch(r"[a-z0-9_]+", str(tag)) for tag in target["tags"]
        ):
            raise FootprintError(f"invalid tags for {target['id']}")
    return data


def selected_targets(manifest: dict[str, Any], selector: str) -> list[dict[str, Any]]:
    targets = manifest["targets"]
    if selector == "all":
        return targets
    wanted = {item.strip() for item in selector.split(",") if item.strip()}
    known = {target["id"] for target in targets}
    unknown = wanted - known
    if unknown:
        raise FootprintError(f"unknown targets: {', '.join(sorted(unknown))}")
    if not wanted:
        raise FootprintError("select at least one target")
    return [target for target in targets if target["id"] == "full" or target["id"] in wanted]


def verify_source(source: pathlib.Path, manifest: dict[str, Any]) -> str:
    source = source.resolve()
    expected = manifest["source"]
    if not (source / expected["processor_dir"] / "go.mod").is_file():
        raise FootprintError("source is missing the resource-detection processor module")
    commit = command(["git", "rev-parse", "HEAD"], cwd=source).strip()
    if commit != expected["commit"]:
        raise FootprintError(f"source is at {commit}; expected {expected['commit']}")
    if command(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source).strip():
        raise FootprintError("source checkout must be clean, including untracked files")
    remote = command(["git", "remote", "get-url", "origin"], cwd=source).strip()
    allowed = {expected["url"], expected["url"].removesuffix(".git"),
               "git@github.com:oso-team/opentelemetry-collector-contrib.git"}
    if remote not in allowed:
        raise FootprintError("source origin must be the public oso-team Contrib fork")
    return commit


def tool_env(manifest: dict[str, Any], go_binary: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"GOWORK": "off", "GOOS": manifest["platform"]["goos"],
                "GOARCH": manifest["platform"]["goarch"], "GOTOOLCHAIN": "local"})
    resolved_go = shutil.which(go_binary)
    if not resolved_go:
        raise FootprintError(f"Go executable not found: {go_binary}")
    env["PATH"] = f"{pathlib.Path(resolved_go).resolve().parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def parse_go_list(output: str) -> tuple[list[str], list[str], dict[str, int]]:
    modules: set[str] = set()
    packages: set[str] = set()
    module_packages: dict[str, set[str]] = {}
    for line in output.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 2 or not all(fields):
            raise FootprintError(f"unexpected go list line: {line[:120]}")
        package, module = fields
        packages.add(package)
        modules.add(module)
        module_packages.setdefault(module, set()).add(package)
    if not modules:
        raise FootprintError("go list returned no non-standard-library modules")
    return sorted(modules), sorted(packages), {
        module: len(module_packages[module]) for module in sorted(modules)
    }


def measure_source(source: pathlib.Path, manifest: dict[str, Any],
                   target: dict[str, Any], env: dict[str, str], go_binary: str) -> tuple[list[str], list[str], dict[str, int]]:
    tags = ",".join(target["tags"])
    args = [go_binary, "list", "-mod=readonly", "-deps"]
    if tags:
        args.append(f"-tags={tags}")
    args.extend(["-f", "{{if .Module}}{{.ImportPath}}\t{{.Module.Path}}{{end}}", "."])
    output = command(args, cwd=source / manifest["source"]["processor_dir"], env=env)
    return parse_go_list(output)


def build_config(manifest: dict[str, Any], source: pathlib.Path,
                 target: dict[str, Any], output_dir: pathlib.Path) -> str:
    builder = manifest["builder"]
    dist = builder["dist"]
    lines = ["dist:"]
    for key in ("module", "name", "description", "version"):
        lines.append(f"  {key}: {json.dumps(dist[key])}")
    lines.append(f"  output_path: {json.dumps(str(output_dir))}")
    if target["tags"]:
        lines.append(f"  build_tags: {json.dumps(','.join(target['tags']))}")
    for component_type, components in builder["components"].items():
        lines.append(f"{component_type}:")
        for module in components:
            lines.append(f"  - gomod: {module}")
    lines.append("replaces:")
    for module, relative in builder["replaces"].items():
        local = source / relative
        if not (local / "go.mod").is_file():
            raise FootprintError(f"replacement module missing: {relative}")
        lines.append(f"  - {module} => {local}")
    return "\n".join(lines) + "\n"


def build_binary(builder_binary: str, config_path: pathlib.Path,
                 output_dir: pathlib.Path, binary_name: str,
                 env: dict[str, str], go_binary: str) -> tuple[int, str]:
    command([builder_binary, "--config", str(config_path), "--ldflags", "-s -w"], env=env)
    binary = output_dir / binary_name
    if not binary.is_file() or binary.stat().st_size == 0:
        raise FootprintError(f"OCB did not produce {binary}")
    metadata = command([go_binary, "version", "-m", str(binary)], env=env)
    if "go.opentelemetry.io/collector" not in metadata:
        raise FootprintError("binary metadata does not identify OpenTelemetry Collector")
    return binary.stat().st_size, metadata


def result_entry(target: dict[str, Any], modules: list[str], packages: list[str],
                 module_packages: dict[str, int],
                 binary_bytes: int | None) -> dict[str, Any]:
    return {"id": target["id"], "label": target["label"],
            "kind": target["kind"], "detectors": target["detectors"],
            "tags": target["tags"], "module_count": len(modules),
            "package_count": len(packages), "binary_bytes": binary_bytes,
            "provenance": {"modules": "measured", "packages": "measured",
                           "binary": "measured" if binary_bytes is not None else "unavailable"},
            "modules": modules, "module_packages": module_packages}


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    targets = selected_targets(manifest, args.targets)
    source = args.source.resolve()
    source_commit = verify_source(source, manifest)
    env = tool_env(manifest, args.go)
    go_version = command([args.go, "version"], env=env).strip()
    if f"go{manifest['platform']['go_version']} " not in go_version:
        raise FootprintError(f"Go toolchain mismatch: expected {manifest['platform']['go_version']}, got {go_version}")
    if not args.no_build and not shutil.which(args.builder):
        raise FootprintError(f"OCB not found: {args.builder}")
    if not args.no_build:
        builder_version = command([args.builder, "version"], env=env).strip()
        if builder_version != f"ocb version {manifest['builder']['version']}":
            raise FootprintError(f"OCB version mismatch: {builder_version}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for target in targets:
        target_dir = output / "work" / target["id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        modules, packages, module_packages = measure_source(source, manifest, target, env, args.go)
        binary_bytes = None
        if not args.no_build:
            config = build_config(manifest, source, target, target_dir / "dist")
            config_path = target_dir / "builder.yaml"
            config_path.write_text(config, encoding="utf-8")
            binary_bytes, metadata = build_binary(args.builder, config_path,
                                                   target_dir / "dist",
                                                   manifest["builder"]["dist"]["name"], env, args.go)
            evidence_dir = output / "evidence" / target["id"]
            evidence_dir.mkdir(parents=True, exist_ok=True)
            portable = config.replace(str(source), "${PUBLIC_CONTRIB_CHECKOUT}")
            portable = portable.replace(str(target_dir / "dist"), "${BUILD_OUTPUT}")
            (evidence_dir / "builder.yaml").write_text(portable, encoding="utf-8")
            portable_metadata = metadata.replace(str(source), "${PUBLIC_CONTRIB_CHECKOUT}")
            portable_metadata = portable_metadata.replace(str(target_dir / "dist"), "${BUILD_OUTPUT}")
            (evidence_dir / "go-version-m.txt").write_text(portable_metadata, encoding="utf-8")
        entries.append(result_entry(target, modules, packages, module_packages, binary_bytes))
        print(f"{target['id']}: {len(modules)} modules, {len(packages)} packages, "
              f"{binary_bytes if binary_bytes is not None else 'no binary'} bytes", flush=True)
    report = {"schema_version": 1,
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "data_kind": "measured" if not args.no_build else "partial",
              "context": {"repo": "oso-team/opentelemetry-collector-contrib",
                          "branch": manifest["source"].get("branch"),
                          "commit": source_commit, "go": go_version,
                          "goos": env["GOOS"], "goarch": env["GOARCH"],
                          "ldflags": "-s -w", "builder": manifest["builder"]["version"],
                          "notes": REPORT_NOTES},
              "baseline": entries[0], "builds": entries[1:]}
    write_json(output / "results.json", report)
    print(f"Wrote {output / 'results.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", type=pathlib.Path, required=True,
                        help="clean checkout of the pinned public Contrib fork")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / ".runs" / "latest")
    parser.add_argument("--targets", default="all", help="all or comma-separated target IDs")
    parser.add_argument("--builder", default="builder", help="path to an approved OCB executable")
    parser.add_argument("--go", default="go", help="Go executable matching platform.go_version")
    parser.add_argument("--no-build", action="store_true",
                        help="measure source reachability without producing Collector binaries")
    args = parser.parse_args()
    try:
        run(args)
    except (FootprintError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
