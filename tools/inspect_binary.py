#!/usr/bin/env python3
"""Check each measured executable without running vendor detectors."""
from __future__ import annotations
import json
import pathlib
import subprocess

from footprint import FootprintError, command, write_json


PROBE_CONFIG = '''receivers:
  otlp:
    protocols:
      http:
        endpoint: 127.0.0.1:0
processors:
  resource_detection:
    detectors: []
    retry:
      enabled: false
exporters:
  debug: {}
service:
  telemetry:
    logs:
      level: debug
      encoding: json
    metrics:
      level: none
    traces:
      level: none
  pipelines:
    logs:
      receivers: [otlp]
      processors: [resource_detection]
      exporters: [debug]
'''


def expected_detectors(target, catalog):
    names = sorted(catalog) if target['kind'] == 'full' else sorted(
        name.removeprefix('resourcedetection_') for name in target['detectors'])
    # Upstream retains this deprecated runtime alias for the same implementation.
    return sorted([*names, *(['k8snode'] if 'k8s_api' in names else [])])


def parse_compiled_detectors(output):
    inventories = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and 'compiled_detectors' in event:
            names = event['compiled_detectors']
            if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
                raise FootprintError('invalid compiled_detectors runtime inventory')
            if len(names) != len(set(names)):
                raise FootprintError('duplicate compiled detector names')
            inventories.append(sorted(names))
    if len(inventories) > 1:
        raise FootprintError('ambiguous multiple compiled detector inventories')
    return inventories[0] if inventories else None


def verify_inventory(expected, observed):
    if observed != expected:
        raise FootprintError(f'compiled detector mismatch: expected {expected}, observed {observed}')


def inspect(binary, target, manifest, source, env, go, directory):
    catalog = manifest['detector_catalog']
    expected = expected_detectors(target, catalog)
    components = command([str(binary), 'components'], env=env)
    (directory/'components.txt').write_text(components)
    for component in ('otlp', 'debug', 'resource_detection'):
        if component not in components:
            raise FootprintError('component missing from executable: '+component)
    metadata = command([go, 'version', '-m', str(binary)], env=env)
    embedded = [line.split('\t', 2)[-1].removeprefix('-tags=') for line in metadata.splitlines() if '\tbuild\t-tags=' in line]
    observed_tags = sorted(embedded[0].split(',')) if embedded else []
    if observed_tags != sorted(target['tags']):
        raise FootprintError('embedded build tags differ from target')
    packages = ['./'+item['package'] for item in catalog.values()]
    args = [go, 'list', '-json']
    if target['tags']:
        args += ['-tags='+','.join(target['tags'])]
    raw = command([*args, *packages], cwd=source/manifest['source']['processor_dir'], env=env)
    decoder = json.JSONDecoder(); selected = {}
    while raw.strip():
        package, end = decoder.raw_decode(raw.lstrip()); raw = raw.lstrip()[end:]
        selected[package['ImportPath'].split('/resourcedetectionprocessor/',1)[-1]] = package['GoFiles']
    expected_implementations = set(expected)-{'k8snode'}
    for name, item in catalog.items():
        files = selected[item['package']]
        enabled = item['implementation_file'] in files
        omitted = item['omitted_file'] in files
        if enabled == omitted or enabled != (name in expected_implementations):
            raise FootprintError('source-file detector selection mismatch: '+name)
    write_json(directory/'selected-source-files.json', selected)
    config = directory/'detector-probe.yaml'; config.write_text(PROBE_CONFIG)
    # No detector is configured, so no detector constructor or cloud probe runs.
    # The known empty-detector startup error follows the PR's registry log.
    result = subprocess.run([str(binary), '--config='+str(config)], env=env,
                            capture_output=True, text=True, timeout=15)
    output = result.stdout+result.stderr
    (directory/'detector-probe.log').write_text(output)
    if result.returncode != 1 or 'no detectors succeeded' not in output:
        raise FootprintError('empty-detector probe did not terminate with its expected error')
    observed = parse_compiled_detectors(output)
    runtime_supported = manifest['inspection']['runtime_inventory']
    if runtime_supported:
        verify_inventory(expected, observed)
    elif observed is not None:
        verify_inventory(expected, observed)
    receipt = {'passed': True, 'expected_detectors': expected,
               'reported_compiled_detectors': observed,
               'runtime_inventory_supported': runtime_supported,
               'source_file_selection_verified': True, 'embedded_tags_verified': True,
               'components_command_verified': True,
               'probe': 'empty detector list; expected no-detectors-succeeded startup error; no cloud detector executed'}
    write_json(directory/'inspection.json', receipt)
    return receipt
