#!/usr/bin/env python3
"""Build a portable comparison only from validated, version-matched runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from footprint import load_manifest
from publish import UNPUBLISHABLE_TEXT, validate_report

SETTINGS = ('go_version', 'builder_version', 'collector_experimental', 'collector_stable',
            'otel_go', 'goos', 'goarch', 'goarm64', 'cgo_enabled', 'goflags', 'ldflags', 'gowork')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(directory: Path, lock: dict, lock_hash: str) -> dict:
    manifest = load_manifest(directory / 'manifest.json')
    if manifest['platform']['go_version'] != lock['go_version'] or manifest['builder']['version'] != lock['builder_version']:
        raise ValueError('manifest tool version drift')
    for modules in manifest['builder']['components'].values():
        if any(module.rsplit(' ', 1)[-1] != lock['collector_experimental'] for module in modules):
            raise ValueError('manifest component version drift')
    report = json.loads((directory / 'results.json').read_text())
    entries = [report['baseline'], *report['builds']]
    ids = [entry['id'] for entry in entries]
    # A selected run is a complete experiment for its explicitly selected targets.
    manifest['targets'] = [target for target in manifest['targets'] if target['id'] in ids]
    validate_report(report, manifest)
    before = json.loads((directory / 'versions-before.json').read_text())
    after = json.loads((directory / 'versions-after.json').read_text())
    for checkpoint in (before, after):
        if checkpoint['source_commit'] != manifest['source']['commit'] or checkpoint['lock_sha256'] != lock_hash:
            raise ValueError('source or version-lock drift')
        env = checkpoint['go_env']
        expected = {'GOVERSION': 'go' + lock['go_version'], 'GOTOOLCHAIN': 'local',
                    'GOOS': lock['goos'], 'GOARCH': lock['goarch'], 'GOARM64': lock['goarm64'],
                    'CGO_ENABLED': lock['cgo_enabled'], 'GOFLAGS': lock['goflags'], 'GOWORK': ''}
        # GOWORK=off is reported as "off" by Go, rather than an absolute path.
        expected['GOWORK'] = 'off'
        if env != expected:
            raise ValueError('build environment differs from the comparison lock')
    if before['module_file_sha256'] != after['module_file_sha256']:
        raise ValueError('module files changed during the experiment')
    if before['tool_sha256'] != after['tool_sha256']:
        raise ValueError('tool executables changed during the experiment')
    modules = json.loads((directory / 'resolved-versions.json').read_text())
    for name, version in modules.items():
        if name.startswith('go.opentelemetry.io/collector/') and version not in (lock['collector_experimental'], lock['collector_stable']):
            raise ValueError('Collector module drift: ' + name)
    if modules['go.opentelemetry.io/otel'] != lock['otel_go']:
        raise ValueError('OpenTelemetry SDK drift')
    receipts = json.loads((directory / 'binary-receipts.json').read_text())
    for entry in entries:
        receipt = receipts[entry['id']]
        if receipt['bytes'] != entry['binary_bytes']:
            raise ValueError('binary size disagrees with its receipt')
        if lock.get('require_detector_inspection'):
            from inspect_binary import expected_detectors, verify_inventory
            inspection = receipt.get('inspection', {})
            if not all(inspection.get(key) is True for key in ('passed', 'source_file_selection_verified', 'embedded_tags_verified', 'components_command_verified')):
                raise ValueError('missing or failed detector inspection')
            expected = expected_detectors(entry, manifest['detector_catalog'])
            verify_inventory(expected, inspection.get('expected_detectors'))
            if manifest['inspection']['runtime_inventory']:
                verify_inventory(expected, inspection.get('reported_compiled_detectors'))
        metadata = receipt['build_metadata']
        if ': go' + lock['go_version'] + '\n' not in metadata:
            raise ValueError('embedded binary Go version differs')
        for setting in ('CGO_ENABLED=' + lock['cgo_enabled'], 'GOOS=' + lock['goos'],
                        'GOARCH=' + lock['goarch'], 'GOARM64=' + lock['goarm64'], '-trimpath=true'):
            if '\tbuild\t' + setting not in metadata.splitlines():
                raise ValueError('embedded binary build setting differs: ' + setting)
        if sha256(directory / 'work' / entry['id'] / 'dist' / manifest['builder']['dist']['name']) != receipt['sha256']:
            raise ValueError('binary checksum differs')
    public_receipts = {name: {key: receipt[key] for key in ('sha256', 'bytes', 'inspection') if key in receipt} for name, receipt in receipts.items()}
    return {'manifest': manifest, 'report': report, 'binary_receipts': public_receipts,
            'tool_sha256': before['tool_sha256'],
            'resolved_versions': modules,
            'evidence_hashes': {name: sha256(directory / name) for name in
                                ('manifest.json', 'results.json', 'versions-before.json', 'versions-after.json', 'binary-receipts.json')}}


def assemble(runs: dict, settings: dict, upstream_commit: str) -> dict:
    upstream = runs['upstream']; unified = runs['unified']
    if upstream['manifest']['source']['commit'] != upstream_commit:
        raise ValueError('upstream base mismatch')
    if any(run['resolved_versions'] != upstream['resolved_versions'] for run in runs.values()):
        raise ValueError('resolved module versions differ across source runs')
    if any(run['tool_sha256'] != upstream['tool_sha256'] for run in runs.values()):
        raise ValueError('tool executables differ across source runs')
    if any(run['manifest']['builder'] != upstream['manifest']['builder'] for run in runs.values()):
        raise ValueError('Collector composition differs across source runs')
    def by_id(run):
        report = run['report']
        return {entry['id']: entry for entry in [report['baseline'], *report['builds']]}
    a, b = by_id(upstream), by_id(unified)
    if set(a) != set(b):
        raise ValueError('strategies must measure the same target set')
    rows = []
    control = by_id(runs['control']) if 'control' in runs else {}
    for target in upstream['manifest']['targets'][1:]:
        name = target['id']
        if a[name]['detectors'] != b[name]['detectors']:
            raise ValueError('logical detector selection differs: ' + name)
        row = {'id': name, 'label': target['label'], 'detectors': target['detectors'],
               'default': {'run': 'upstream', 'id': 'full'},
               'optout': {'run': 'upstream', 'id': name},
               'unified': {'run': 'unified', 'id': name}}
        if name in control:
            row['control'] = {'run': 'control', 'id': name}
        rows.append(row)
    result = {'schema_version': 1, 'experiment': 'rdp-unified-tags', 'settings': settings,
              'upstream_commit': upstream_commit, 'runs': runs, 'rows': rows,
              'notes': ['Default means the same minimal OTLP/RDP/debug Collector with every RDP detector compiled.',
                        'Module and package counts measure source reachability from RDP. Binary bytes measure the complete stripped Collector.',
                        'Every strategy uses the recorded Go/OCB/component versions and build settings. Historical measurements are not mixed into this comparison.',
                        'Exact measured source revisions are pinned; later test and documentation commits do not relabel these measurements.']}
    if UNPUBLISHABLE_TEXT.search(json.dumps(result)):
        raise ValueError('comparison contains a private path, endpoint, or credential marker')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--unified', type=Path, required=True)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--site-index', type=Path, help='also render the current report as the site homepage')
    args = parser.parse_args()
    try:
        lock = json.loads(args.lock.read_text())
        runs = {name: load_run(directory, lock, sha256(args.lock)) for name, directory in
                [('upstream', args.upstream), ('unified', args.unified), ('control', args.control)] if directory}
        report = assemble(runs, {key: lock[key] for key in SETTINGS}, lock['upstream_commit'])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        if args.html or args.site_index:
            template = (Path(__file__).resolve().parents[1] / 'templates/comparison.html').read_text()
            payload = json.dumps(report, separators=(',', ':')).replace('<', '\\u003c')
            html = template.replace('COMPARISON_DATA', payload)
            for destination in (args.html, args.site_index):
                if destination:
                    destination.write_text(html)
        print(f"Validated {len(report['rows'])} matched detector selections across {len(runs)} source runs")
    except (OSError, ValueError, KeyError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
