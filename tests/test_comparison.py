import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import compare


class ComparisonEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        manifest = json.loads((ROOT / 'experiment.json').read_text())
        report = json.loads((ROOT / 'docs/results.json').read_text())
        manifest['targets'] = manifest['targets'][:2]
        report['builds'] = report['builds'][:1]
        settings = dict(go_version=manifest['platform']['go_version'], builder_version=manifest['builder']['version'],
                        collector_experimental=manifest['builder']['version'], collector_stable='v1.67.0',
                        otel_go='v1.47.0', goos='darwin', goarch='arm64', goarm64='v8.0',
                        cgo_enabled='0', goflags='-p=3 -trimpath', ldflags='-s -w', gowork='off')
        # Unit-test fixture: tiny binaries and deliberately synthetic metadata.
        for kind, modules in manifest['builder']['components'].items():
            manifest['builder']['components'][kind] = [module.rsplit(' ', 1)[0] + ' ' + settings['collector_experimental'] for module in modules]
        self.lock = settings
        self.lock_hash = 'unit-test-lock'
        checkpoint = {'source_commit': manifest['source']['commit'], 'lock_sha256': self.lock_hash,
                      'tool_sha256': {'go': 'same-go', 'builder': 'same-builder'},
                      'module_file_sha256': {'go.mod': 'unchanged'},
                      'go_env': dict(GOVERSION='go'+settings['go_version'], GOTOOLCHAIN='local', GOWORK='off',
                                     GOOS='darwin', GOARCH='arm64', GOARM64='v8.0', CGO_ENABLED='0', GOFLAGS=settings['goflags'])}
        self.write('manifest.json', manifest)
        receipts = {}
        for entry in [report['baseline'], *report['builds']]:
            entry['binary_bytes'] = 4
            binary = self.directory / 'work' / entry['id'] / 'dist' / manifest['builder']['dist']['name']
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'test')
            receipts[entry['id']] = {'bytes': 4, 'sha256': hashlib.sha256(b'test').hexdigest(),
                                     'build_metadata': 'fixture: go'+settings['go_version']+'\n' + '\n'.join(
                                         '\tbuild\t'+value for value in ('CGO_ENABLED=0', 'GOOS=darwin', 'GOARCH=arm64', 'GOARM64=v8.0', '-trimpath=true'))}
        self.write('results.json', report)
        self.write('versions-before.json', checkpoint)
        self.write('versions-after.json', checkpoint)
        self.write('resolved-versions.json', {'go.opentelemetry.io/otel': settings['otel_go']})
        self.write('binary-receipts.json', receipts)

    def write(self, name, value):
        (self.directory / name).write_text(json.dumps(value))

    def change(self, name, mutate):
        data = json.loads((self.directory / name).read_text())
        mutate(data)
        self.write(name, data)

    def load(self):
        return compare.load_run(self.directory, self.lock, self.lock_hash)

    def test_accepts_matching_evidence(self):
        self.assertEqual(2, len(self.load()['binary_receipts']))

    def test_rejects_changed_go_environment(self):
        self.change('versions-after.json', lambda d: d['go_env'].update(CGO_ENABLED='1'))
        with self.assertRaisesRegex(ValueError, 'environment'):
            self.load()

    def test_rejects_changed_source(self):
        self.change('versions-after.json', lambda d: d.update(source_commit='0'*40))
        with self.assertRaisesRegex(ValueError, 'source'):
            self.load()

    def test_rejects_changed_module_files(self):
        self.change('versions-after.json', lambda d: d['module_file_sha256'].update({'go.mod': 'changed'}))
        with self.assertRaisesRegex(ValueError, 'module files'):
            self.load()

    def test_rejects_changed_sdk(self):
        self.change('resolved-versions.json', lambda d: d.update({'go.opentelemetry.io/otel': 'v1.0.0'}))
        with self.assertRaisesRegex(ValueError, 'SDK'):
            self.load()

    def test_rejects_changed_binary_metadata(self):
        self.change('binary-receipts.json', lambda d: d['full'].update(build_metadata=d['full']['build_metadata'].replace('CGO_ENABLED=0', 'CGO_ENABLED=1')))
        with self.assertRaisesRegex(ValueError, 'build setting'):
            self.load()

    def test_rejects_changed_binary(self):
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        binary = self.directory / 'work/full/dist' / manifest['builder']['dist']['name']
        binary.write_bytes(b'evil')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.load()

    def test_rejects_cross_run_dependency_drift(self):
        a = self.load(); b = copy.deepcopy(a)
        b['resolved_versions']['example.com/sdk'] = 'v9.0.0'
        with self.assertRaisesRegex(ValueError, 'module versions differ'):
            compare.assemble({'upstream': a, 'unified': b}, self.lock, a['manifest']['source']['commit'])


if __name__ == '__main__':
    unittest.main()
