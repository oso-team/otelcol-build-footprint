#!/usr/bin/env python3
"""Measure one source revision with fail-closed version and binary receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import footprint


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_stream(text: str) -> list[dict]:
    decoder = json.JSONDecoder(); remaining = text; result = []
    while remaining.strip():
        item, end = decoder.raw_decode(remaining.lstrip())
        remaining = remaining.lstrip()[end:]
        result.append(item)
    return result


def run(args: argparse.Namespace) -> None:
    args.manifest = args.manifest.resolve()
    args.lock = args.lock.resolve()
    manifest = footprint.load_manifest(args.manifest)
    lock = json.loads(args.lock.read_text())
    source = args.source.resolve(); output = args.output.resolve()
    go = str(args.go.resolve()); builder = str(args.builder.resolve())
    footprint.verify_source(source, manifest)
    if manifest['platform'] != {key: lock[key] for key in ('goos', 'goarch')} | {'go_version': lock['go_version']}:
        raise ValueError('manifest platform/toolchain differs from lock')
    if manifest['builder']['version'] != lock['builder_version']:
        raise ValueError('manifest OCB differs from lock')
    for modules in manifest['builder']['components'].values():
        if any(module.rsplit(' ', 1)[-1] != lock['collector_experimental'] for module in modules):
            raise ValueError('manifest component differs from lock')
    output.mkdir(parents=True, exist_ok=False)
    env = footprint.tool_env(manifest, go)
    env.update(CGO_ENABLED=lock['cgo_enabled'], GOFLAGS=lock['goflags'], GOARM64=lock['goarm64'],
               GOMAXPROCS='3', LLVM_PROFILE_FILE=str(output/'tool-%p.profraw'))
    def command(command_args, cwd=source):
        return footprint.command(command_args, cwd=cwd, env=env).strip()
    if command([go, 'version']).split()[2] != 'go'+lock['go_version']:
        raise ValueError('Go executable version drift')
    if command([builder, 'version']) != 'ocb version '+lock['builder_version']:
        raise ValueError('OCB executable version drift')
    builder_metadata=command([go,'version','-m',builder])
    builder_go=builder_metadata.splitlines()[0].rsplit(' ',1)[-1].removeprefix('go')
    if 'builder_go_version' in lock and builder_go != lock['builder_go_version']:
        raise ValueError('OCB compiler version drift')
    footprint.write_json(output/'tool-versions.json',{'go':command([go,'version']),
                         'builder':command([builder,'version']), 'builder_go_version':builder_go})
    for path, key in ((Path(go), 'go_sha256'), (Path(builder), 'builder_sha256')):
        if key in lock and digest(path) != lock[key]:
            raise ValueError(key+' mismatch')
    files = command(['git', 'ls-files', '--', '*go.mod', '*go.sum']).splitlines()
    def checkpoint(name):
        footprint.verify_source(source, manifest)
        data = {'source_commit': command(['git', 'rev-parse', 'HEAD']),
                'lock_sha256': digest(args.lock),
                'go_env': json.loads(command([go, 'env', '-json', 'GOVERSION', 'GOTOOLCHAIN', 'GOWORK', 'GOOS', 'GOARCH', 'GOARM64', 'CGO_ENABLED', 'GOFLAGS'])),
                'module_file_sha256': {file: digest(source/file) for file in files},
                'tool_sha256': {'go': digest(Path(go)), 'builder': digest(Path(builder))},
                'benchmark_code_sha256': {path.name: digest(path) for path in Path(__file__).parent.glob('*.py')}}
        footprint.write_json(output/(name+'.json'), data)
        return data
    before = checkpoint('versions-before')
    footprint.write_json(output/'manifest.json', manifest)
    raw = command([go, 'list', '-mod=readonly', '-m', '-json', 'all'], source/manifest['source']['processor_dir'])
    (output/'resolved-source-modules.jsonstream').write_text(raw+'\n')
    modules = {module['Path']: module.get('Version', 'local') for module in json_stream(raw)}
    for name, version in modules.items():
        if name.startswith('go.opentelemetry.io/collector/') and version not in (lock['collector_experimental'], lock['collector_stable']):
            raise ValueError('resolved Collector version drift: '+name)
    if modules['go.opentelemetry.io/otel'] != lock['otel_go']:
        raise ValueError('resolved OpenTelemetry SDK version drift')
    footprint.write_json(output/'resolved-versions.json', modules)
    original_env = dict(os.environ); original_cwd = Path.cwd()
    try:
        os.environ.update(env); os.chdir(output)
        footprint.run(argparse.Namespace(manifest=args.manifest.resolve(), source=source, output=output,
                                        targets=args.targets, go=go, builder=builder, no_build=False))
    finally:
        os.chdir(original_cwd); os.environ.clear(); os.environ.update(original_env)
    after = checkpoint('versions-after')
    for key in ('source_commit', 'lock_sha256', 'go_env', 'module_file_sha256', 'tool_sha256', 'benchmark_code_sha256'):
        if before[key] != after[key]:
            raise ValueError('phase drift: '+key)
    receipts = {}
    for binary in (output/'work').glob('*/dist/'+manifest['builder']['dist']['name']):
        metadata = command([go, 'version', '-m', str(binary)])
        if ': go'+lock['go_version']+'\n' not in metadata:
            raise ValueError('embedded Go version drift')
        for setting in ('CGO_ENABLED='+lock['cgo_enabled'], 'GOOS='+lock['goos'], 'GOARCH='+lock['goarch'], 'GOARM64='+lock['goarm64'], '-trimpath=true'):
            if '\tbuild\t'+setting not in metadata.splitlines():
                raise ValueError('embedded build setting drift: '+setting)
        for module in ('collector/otelcol', 'collector/service', 'collector/receiver/otlpreceiver', 'collector/exporter/debugexporter'):
            if '\tdep\tgo.opentelemetry.io/'+module+'\t'+lock['collector_experimental']+'\t' not in metadata:
                raise ValueError('embedded Collector module drift: '+module)
        receipts[binary.parent.parent.name] = {'sha256': digest(binary), 'bytes': binary.stat().st_size, 'build_metadata': metadata}
    if lock.get('require_detector_inspection'):
        inspections = json.loads((output/'binary-inspections.json').read_text())
        for name, receipt in receipts.items():
            receipt['inspection'] = inspections[name]
    footprint.write_json(output/'binary-receipts.json', receipts)
    print('PASS source, tool, module, runner, environment and binary provenance', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('manifest', 'lock', 'source', 'output', 'go', 'builder'):
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--targets', default='all')
    try:
        run(parser.parse_args())
    except (OSError, ValueError, KeyError, footprint.FootprintError) as exc:
        print('error: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
