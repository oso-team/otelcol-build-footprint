import json
import copy
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from footprint import REPORT_NOTES, FootprintError, build_config, load_manifest, parse_go_list, selected_targets  # noqa: E402
from publish import HTML_DATA_CLOSE, HTML_DATA_OPEN, UNPUBLISHABLE_TEXT, embed_report, validate_report  # noqa: E402


class ExperimentContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest(ROOT / "experiment.json")

    def test_target_matrix_has_baseline_and_unique_builds(self):
        targets = selected_targets(self.manifest, "all")
        self.assertEqual(42, len(targets))
        self.assertEqual("full", targets[0]["id"])
        self.assertEqual(42, len({target["id"] for target in targets}))
        self.assertEqual(["full", "gcp"],
                         [target["id"] for target in selected_targets(self.manifest, "gcp")])
        with self.assertRaises(FootprintError):
            selected_targets(self.manifest, "unknown")

    def test_go_list_parser_deduplicates_packages_and_modules(self):
        modules, packages, module_packages = parse_go_list("p/a\tm/one\np/b\tm/one\np/a\tm/one\np/c\tm/two\n")
        self.assertEqual(["m/one", "m/two"], modules)
        self.assertEqual(["p/a", "p/b", "p/c"], packages)
        self.assertEqual({"m/one": 2, "m/two": 1}, module_packages)
        with self.assertRaises(FootprintError):
            parse_go_list("malformed\n")

    def test_builder_manifest_uses_only_pinned_public_modules_and_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory)
            for relative in self.manifest["builder"]["replaces"].values():
                module_dir = source / relative
                module_dir.mkdir(parents=True)
                (module_dir / "go.mod").write_text("module example.test\n")
            target = next(t for t in self.manifest["targets"] if t["id"] == "gcp")
            config = build_config(self.manifest, source, target, source / "output")
            self.assertIn("enable_resourcedetection_gcp_detector", config)
            self.assertIn("github.com/open-telemetry/opentelemetry-collector-contrib", config)
            self.assertEqual(3, config.count(" => "))

    def test_published_report_is_measured_and_internally_consistent(self):
        report = json.loads((ROOT / "docs" / "results.json").read_text())
        self.assertEqual("measured", report["data_kind"])
        self.assertEqual(41, len(report["builds"]))
        validate_report(report, self.manifest)
        for build in [report["baseline"], *report["builds"]]:
            self.assertEqual(build["module_count"], len(build["modules"]))
            self.assertEqual(build["package_count"], sum(build["module_packages"].values()))
            self.assertGreater(build["binary_bytes"], 0)

    def test_publication_rejects_local_path_and_unmeasured_binary(self):
        report = json.loads((ROOT / "docs" / "results.json").read_text())
        report["context"]["notes"] = "/Users/someone/benchmark"
        with self.assertRaisesRegex(ValueError, "local path"):
            validate_report(report, self.manifest)
        report["context"]["notes"] = REPORT_NOTES
        report["baseline"]["binary_bytes"] = None
        with self.assertRaisesRegex(ValueError, "missing binary"):
            validate_report(report, self.manifest)
        incomplete = copy.deepcopy(report)
        incomplete["baseline"]["binary_bytes"] = 100
        incomplete["builds"].pop()
        with self.assertRaisesRegex(ValueError, "every pinned build"):
            validate_report(incomplete, self.manifest)

    def test_publication_rejects_incomplete_module_package_counts(self):
        report = json.loads((ROOT / "docs" / "results.json").read_text())
        first_module = report["builds"][0]["modules"][0]
        del report["builds"][0]["module_packages"][first_module]
        with self.assertRaisesRegex(ValueError, "module package counts mismatch"):
            validate_report(report, self.manifest)

    def test_publication_rejects_unexpected_report_text(self):
        report = json.loads((ROOT / "docs" / "results.json").read_text())
        report["context"]["notes"] = "Unrelated text"
        with self.assertRaisesRegex(ValueError, "report context does not match"):
            validate_report(report, self.manifest)
        report["context"]["notes"] = REPORT_NOTES
        report["extra"] = "Unrelated text"
        with self.assertRaisesRegex(ValueError, "unexpected report fields"):
            validate_report(report, self.manifest)

    def test_standalone_html_contains_the_measured_public_dataset(self):
        report = json.loads((ROOT / "docs" / "results.json").read_text())
        html = (ROOT / "docs" / "index.html").read_text()
        embedded = html.split(HTML_DATA_OPEN, 1)[1].split(HTML_DATA_CLOSE, 1)[0]
        self.assertEqual(report, json.loads(embedded))
        self.assertIsNone(UNPUBLISHABLE_TEXT.search(html))
        self.assertEqual(html, embed_report(html, report))

    def test_html_embedding_escapes_script_terminators(self):
        html = HTML_DATA_OPEN + "{}" + HTML_DATA_CLOSE
        embedded = embed_report(html, {"note": "</script>"})
        self.assertNotIn("</script>", embedded.split(HTML_DATA_OPEN, 1)[1].split(HTML_DATA_CLOSE, 1)[0])
        self.assertEqual({"note": "</script>"}, json.loads(embedded.split(HTML_DATA_OPEN, 1)[1].split(HTML_DATA_CLOSE, 1)[0]))


if __name__ == "__main__":
    unittest.main()
