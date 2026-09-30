#!/usr/bin/env python3
"""Validate a measured run before replacing the GitHub Pages dataset."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

from footprint import DEFAULT_MANIFEST, REPORT_NOTES, ROOT, load_manifest


UNPUBLISHABLE_TEXT = re.compile(
    r"/(?:Users|home)/[^/]+/|"
    r"https?://[^\s/]+\.(?:internal|corp|private)(?:[/:]|\b)|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
HTML_DATA_OPEN = '<script id="rdp-data" type="application/json">\n'
HTML_DATA_CLOSE = '\n</script>'


def embed_report(html: str, report: dict) -> str:
    """Keep the original standalone report usable without an HTTP server."""
    if html.count(HTML_DATA_OPEN) != 1:
        raise ValueError("report HTML must have exactly one embedded data block")
    start = html.index(HTML_DATA_OPEN) + len(HTML_DATA_OPEN)
    end = html.index(HTML_DATA_CLOSE, start)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    return html[:start] + payload + html[end:]


def validate_report(report: dict, manifest: dict) -> None:
    if report.get("schema_version") != 1 or report.get("data_kind") != "measured":
        raise ValueError("only complete measured schema-v1 results can be published")
    serialized = json.dumps(report, ensure_ascii=False)
    match = UNPUBLISHABLE_TEXT.search(serialized)
    if match:
        raise ValueError(f"report contains a local path, restricted endpoint, or credential marker: {match.group(0)}")
    if set(report) != {"schema_version", "data_kind", "generated_at", "context", "baseline", "builds"}:
        raise ValueError("unexpected report fields")
    try:
        generated_at = dt.datetime.fromisoformat(report["generated_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid result timestamp") from exc
    if generated_at.tzinfo is None:
        raise ValueError("result timestamp must include a time zone")
    context = report.get("context", {})
    if set(context) != {"repo", "branch", "commit", "go", "goos", "goarch", "ldflags", "builder", "notes"}:
        raise ValueError("unexpected report context fields")
    if context.get("notes") != REPORT_NOTES or context.get("ldflags") != "-s -w":
        raise ValueError("report context does not match the pinned experiment")
    if context.get("repo") != "oso-team/opentelemetry-collector-contrib":
        raise ValueError("report source is not the public Contrib fork")
    if context.get("commit") != manifest["source"]["commit"]:
        raise ValueError("report source commit does not match the pinned experiment")
    if context.get("branch") != manifest["source"].get("branch"):
        raise ValueError("report branch does not match the pinned experiment")
    if context.get("builder") != manifest["builder"]["version"]:
        raise ValueError("report OCB version does not match the pinned experiment")
    if context.get("goos") != manifest["platform"]["goos"] or context.get("goarch") != manifest["platform"]["goarch"]:
        raise ValueError("report platform does not match the pinned experiment")
    expected_go = f"go version go{manifest['platform']['go_version']} {context['goos']}/{context['goarch']}"
    if context.get("go") != expected_go:
        raise ValueError("report Go version does not match the pinned experiment")
    expected_ids = [target["id"] for target in manifest["targets"]]
    entries = [report.get("baseline"), *report.get("builds", [])]
    if not entries or entries[0] is None or entries[0].get("id") != "full":
        raise ValueError("missing full baseline")
    ids = [entry.get("id") for entry in entries]
    if ids != expected_ids:
        raise ValueError("report must contain every pinned build in manifest order")
    baseline_modules = set(entries[0]["modules"])
    for entry, target in zip(entries, manifest["targets"]):
        if set(entry) != {"id", "label", "kind", "detectors", "tags", "module_count", "package_count",
                          "binary_bytes", "provenance", "modules", "module_packages"}:
            raise ValueError(f"unexpected build fields: {entry.get('id')}")
        if entry.get("label") != target["label"] or entry.get("detectors") != target["detectors"]:
            raise ValueError(f"build description mismatch: {entry.get('id')}")
        if entry.get("tags") != target["tags"] or entry.get("kind") != target["kind"]:
            raise ValueError(f"build configuration mismatch: {entry.get('id')}")
        if entry.get("module_count") != len(entry.get("modules", [])):
            raise ValueError(f"module inventory mismatch: {entry.get('id')}")
        if not set(entry["modules"]).issubset(baseline_modules):
            raise ValueError(f"build includes modules outside the default build: {entry.get('id')}")
        module_packages = entry.get("module_packages", {})
        if set(module_packages) != set(entry["modules"]) or any(
            not isinstance(count, int) or count <= 0 for count in module_packages.values()
        ) or sum(module_packages.values()) != entry.get("package_count"):
            raise ValueError(f"module package counts mismatch: {entry.get('id')}")
        if not isinstance(entry.get("binary_bytes"), int) or entry["binary_bytes"] <= 0:
            raise ValueError(f"missing binary measurement: {entry.get('id')}")
        if set(entry.get("provenance", {}).values()) != {"measured"}:
            raise ValueError(f"non-measured value: {entry.get('id')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=pathlib.Path, help="results.json from tools/footprint.py")
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "docs" / "results.json")
    parser.add_argument("--html-output", type=pathlib.Path, default=ROOT / "docs" / "index.html")
    parser.add_argument("--write", action="store_true", help="replace the Pages dataset after validation")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        report = json.loads(args.results.read_text(encoding="utf-8"))
        validate_report(report, manifest)
        print(f"Validated {1 + len(report['builds'])} measured builds")
        if args.write:
            html = embed_report(args.html_output.read_text(encoding="utf-8"), report)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(args.output)
            html_temporary = args.html_output.with_suffix(".html.tmp")
            html_temporary.write_text(html, encoding="utf-8")
            html_temporary.replace(args.html_output)
            print(f"Updated {args.output}")
            print(f"Embedded data in {args.html_output}")
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
