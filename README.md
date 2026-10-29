# Collector build footprint

Reproducible measurements of OpenTelemetry Collector dependencies and binary size.

The [current interactive report](https://oso-team.github.io/otelcol-build-footprint/) tells the combined contribution story: all detectors, Codeboten’s omission tags before configuration decoupling, and the completed lightweight-configuration/opt-in work in [PR #52063](https://github.com/open-telemetry/opentelemetry-collector-contrib/pull/52063) plus its EC2 and Kubernetes prerequisites. The [comparison URL](https://oso-team.github.io/otelcol-build-footprint/comparison.html) serves the same report. Both work offline.

The separate [parent PR versus current main comparison](https://oso-team.github.io/otelcol-build-footprint/current-main/) answers a different question. The EC2 and Kubernetes fixes have already merged, so that view correctly shows the smaller remaining parent-PR delta.

A resource detector adds information about where telemetry runs, such as a cloud region or host name. Build tags choose which implementations Go compiles. YAML chooses which compiled detectors run. Selecting fewer detectors in YAML does not remove the other implementations from the executable.

## What the comparison establishes

Upstream already supports omitting detector implementations with build tags. The PR builds on that implementation/omitted-file pattern. It adds a global remove-all tag and individual enable tags, while retaining the existing omit tags.

Configuration code can retain provider SDK imports after implementations are omitted. The EC2 retry-default fix (#52170), lightweight Kubernetes configuration types (#52313), and parent PR’s GCP helper change remove these paths. The parent also adds explicit opt-in selection. Tag syntax itself does not cause the extra size reduction.

| Stage | Source and selection |
| --- | --- |
| All detectors · SDK-coupled configs | Pinned upstream plus the reconstruction patch, without detector tags |
| Omit tags · SDK-coupled configs | Same reconstructed source with every unwanted implementation omitted |
| Opt-in · lightweight configs | Pinned parent PR, including both merged prerequisites, with the same detector selection |

Stages one and two are a **controlled reconstruction**, not an untouched historical release. The public [source patch](experiments/config-decoupling-story/sdk-coupled-configs.patch) reverses only the Go/schema changes in the EC2 and Kubernetes prerequisite commits. It keeps modern dependency pins, upstream omission machinery and unrelated source changes fixed. This isolates the combined work without conflating it with weeks of unrelated upgrades. It does not separately attribute each byte to an individual fix.

The patch includes the EKS configuration path, which began using the shared Kubernetes config during review. All-detector builds and selections that still use these SDKs can show little or no improvement; exact values and increases remain visible.

## Current measured data

[docs/comparison.json](docs/comparison.json) records 41 matched detector selections. The source commits are:

| Source | Measured commit |
| --- | --- |
| Upstream base for reconstructed stages 1/2 | 6411c22b92c0b3819b709917e70c989798a3caca |
| PR implementation | f2359adce5e5daf15b6987d6cd23bf83e6c80290 |

The base SHA alone is not the reconstructed source: apply the SHA-256-verified patch recorded in the manifest. These are pinned measurements, not live branch heads. Later test and documentation changes do not relabel them. Previous October 15 measurements are preserved in the [interactive archive](https://oso-team.github.io/otelcol-build-footprint/archive-2026-10-15/) with their [original manifests](experiments/archive-2026-10-15/). They are not mixed into the refreshed comparison.

[experiments/config-decoupling-story/versions.lock.json](experiments/config-decoupling-story/versions.lock.json) records Go 1.27.2, OCB/Collector experimental 0.164.0, Core stable 1.70.0, OpenTelemetry Go 1.47.0, and the build settings. Every run uses the same tools, component composition, resolved versions and Darwin/ARM64 platform. Linux/AMD64 OKE smoke tests are separate runtime evidence.

The runner uses Python's standard library, Git, Go, and the [OpenTelemetry Collector Builder (OCB)](https://opentelemetry.io/docs/collector/extend/ocb/). The report uses browser standard libraries. No Python or JavaScript package installation is required.

## Matched upstream and PR comparison

Select a manifest's exact source commit in your existing Contrib checkout, then run:

~~~sh
python3 tools/locked_run.py \
  --manifest experiments/config-decoupling-story/unified.json \
  --lock experiments/config-decoupling-story/versions.lock.json \
  --source /path/to/contrib \
  --output /path/to/new-run \
  --go /path/to/go-1.27.2/bin/go \
  --builder /path/to/ocb-0.164.0-built-with-go-1.27.2
~~~

For stages 1/2, select the pinned upstream commit in a clean existing checkout and apply the public reconstruction patch before running the upstream manifest:

~~~sh
git apply /path/to/otelcol-build-footprint/experiments/config-decoupling-story/sdk-coupled-configs.patch
~~~

Repeat the runner with `--manifest experiments/config-decoupling-story/upstream.json`, using the same executables and settings. Reverse that exact patch afterward with `git apply --reverse` before switching source revisions. Pass --targets ec2,oraclecloud for a small first run. Internal manifest and dataset names such as unified and optout remain stable for reproducibility and existing shared URLs; they are not claims about what causes the savings.

The runner rejects dirty or incorrect source (except the exact, checksum-verified reconstruction patch declared in the manifest), mismatched versions, changed module files or measurement code, tool replacement, and incorrect embedded binary settings. It records tool hashes, resolved module versions, before/after checkpoints, and every binary checksum. Generated binaries and raw local paths remain ignored under .runs/.

Combine the completed matched runs and render both current pages:

~~~sh
python3 tools/compare.py \
  --upstream /path/to/upstream-run \
  --unified /path/to/pr-run \
  --lock experiments/config-decoupling-story/versions.lock.json \
  --output docs/comparison.json \
  --html docs/comparison.html \
  --site-index docs/index.html
~~~

The current story rebuilds 42 reconstructed upstream binaries and reuses the 42 unchanged PR binaries from the preceding refresh. It revalidates their original checksums, timestamps, tool versions, dependency resolutions and composition receipts; it does not relabel when they were measured. The version-lock bytes are identical across the refresh and this reconstruction. Older controls remain in the October 15 archive with their original versions and source revisions.

The comparison validates each selected target set with the publication contract. It requires identical tools, component composition and resolved module versions across runs. It rejects local paths in exported data.

## Binary composition checks

All 84 measured executables have passed their composition inspections; every checksum and inspection receipt is revalidated before publication. `components` verifies that the expected OTLP receiver, RDP and debug exporter are available. It does not list nested resource detectors. The runner also checks each executable’s embedded build tags and Go’s selected implementation/stub files for all 32 detector implementations.

The PR’s debug startup log includes `compiled_detectors`. A bounded local probe uses `detectors: []`, `retry.enabled: false` and debug logging. It checks the reported names exactly, including the deprecated `k8snode` alias when `k8s_api` is included. No detector is configured, so no cloud constructor or metadata detection runs. The resulting `no detectors succeeded` startup error is intentional; this probe is not a readiness test.

Upstream does not expose the per-detector runtime list. Its binaries pass the components, embedded-tag and source-file checks; the report does not claim runtime inventory reporting for upstream. Local raw logs and selected-file receipts are retained with the run. Portable inspection summaries are embedded alongside each binary checksum in `docs/comparison.json` and shown in the build detail view. Publication rejects missing or failed required inspections.

These checks verify composition, not behavior in each cloud environment. The separate real-OKE default/Oracle-only smoke tests remain functional evidence, not part of this Darwin/arm64 size comparison.

## Measurement definitions

| Measure | Scope | Collection |
| --- | --- | --- |
| Reachable packages | Resource detection processor | go list -deps under selected tags, excluding standard-library packages |
| Reachable modules | Resource detection processor | Distinct module paths that own those packages |
| Packages per module | Resource detection processor | Count of reachable packages owned by each module |
| Binary size | Complete minimal Collector | Byte size of the OCB-built executable with -s -w linker flags |
| Binary metadata | Complete minimal Collector | go version -m output, stored as portable evidence |

A Go module is a versioned dependency containing packages. Module counts here describe the production imports reachable from RDP, not every dependency of the complete executable. Build tags do not remove requirements from go.mod or isolate dependency versions.

Every target uses the same minimal OTLP receiver, resource detection processor and debug exporter. “All detectors” means all RDP implementations, not the full Contrib distribution. Module reachability is not an SBOM, vulnerability result, license determination, or runtime performance measurement. Binary size is not processor-only size.

The grid shows the completed follow-up versus the reconstructed all-detector baseline. Its squares provide module names and package counts on hover, tap, or keyboard focus. The three-way charts show the omission-tag savings and then the additional configuration-decoupling savings for the same selection. The Compare Builds section shows paired omit-tag and completed-follow-up bars for all 41 selections, with the shared all-detector baseline at the top. Hover or focus a bar for an invitation to open its detailed diff.

Each build detail includes detector names, module/package/binary statistics, provider-library categories, exact tags with a copy button, pinned source and manifest links, and the binary checksum. The red/green module diff supports search and package-count details. Completed builds can compare against the all-detector baseline or the reconstructed omit-tag build with the same detector selection. Inspection, comparison baseline, search, build filters, view and metric are stored in the URL. Detector and module filters are stored in the URL.

## September archive

The [historical report](https://oso-team.github.io/otelcol-build-footprint/historical.html) preserves the September measurements and their original implementation explanation. It describes an earlier proposal. It is not evidence for the current implementation or a version-matched comparison with today's upstream.

[docs/results.json](docs/results.json) was produced on 2026-09-28 at commit a5d5f6a7f795bbf53e45ef3a9a2291555c5c17b4, on Darwin/ARM64 with Go 1.26.4 and OCB 0.161.0. It contains a default build and 41 detector selections. The default measured 186 modules and 108,223,826 binary bytes. These historical measurements are not mixed with the current comparison.

To reproduce it, use experiment.json, its exact public source commit, Go 1.26.4, and OCB 0.161.0. The current project Go pin selects the newer comparison toolchain, so pass the historical executable explicitly:

~~~sh
python3 tools/footprint.py \
  --source /path/to/pinned-historical-contrib \
  --targets all \
  --go /path/to/go-1.26.4/bin/go \
  --builder /path/to/ocb-0.161.0
~~~

Validate a complete historical run before replacing its archived data:

~~~sh
python3 tools/publish.py .runs/latest/results.json
python3 tools/publish.py .runs/latest/results.json --write
~~~

The historical publisher updates docs/results.json and docs/historical.html. It does not overwrite the current homepage. The [earlier public report](https://oso-team.github.io/opentelemetry-collector-contrib/) remains available separately.

## Develop and validate the report

GitHub Pages serves docs/ from main. Both current pages embed the same measured story snapshot from templates/comparison.html. The separate current-main comparison retains its original dataset and uses templates/current-main.html; its nested archive links point back to the root archives. The historical report embeds its separate September dataset.

~~~sh
python3 -m unittest discover -s tests -v
python3 tools/publish.py docs/results.json
python3 -m http.server 8000 --directory docs
~~~

Review the generated HTML alongside the template. Check the hero selector, dropdown prompt, module details, filter URLs, exact deltas, light/dark themes, and mobile layout before publishing. Keep source revisions and measurement inputs unchanged when editing presentation.

## Repository layout

| Path | Purpose |
| --- | --- |
| experiments/config-decoupling-story/ | Story manifests, unchanged version lock and exact source reconstruction patch |
| experiments/unified-tags/ | Current-main comparison manifests and version lock |
| docs/current-main/ | Parent PR versus current main; no reconstruction |
| tools/locked_run.py | Version-guarded build runner |
| tools/compare.py | Cross-run validation and current report generation |
| templates/comparison.html | Shared current-report source |
| docs/index.html and docs/comparison.html | Identical current reports |
| experiment.json and tools/footprint.py | Historical pinned experiment |
| tools/publish.py | Historical publication validator |
| docs/historical.html and docs/results.json | Historical report and dataset |
| tests/ | Data contracts and publication checks |

## License and attribution

This repository is licensed under [Apache-2.0](LICENSE). OpenTelemetry Collector and Collector Contrib are separately maintained [Apache-2.0 projects](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/LICENSE). The report's visual foundation comes from the [original public report](https://oso-team.github.io/opentelemetry-collector-contrib/). This project is an independent experiment and is not an official OpenTelemetry distribution.
