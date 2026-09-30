# Collector build footprint

Reproducible OpenTelemetry Collector build comparisons showing how component choices affect dependencies and binary size.

The first experiment compares resource-detection processor builds. A default build includes every detector. Other builds select one detector or a commonly used group through Go build tags. The [interactive report](https://oso-team.github.io/otelcol-build-footprint/) shows module and binary differences for each choice. It benchmarks the public [`rdp-module-split-v4` proposal branch](https://github.com/oso-team/opentelemetry-collector-contrib/tree/rdp-module-split-v4) at an exact commit, before the proposed detector changes are released upstream.

The report UI builds on the [previously published resource-detector report](https://oso-team.github.io/opentelemetry-collector-contrib/). The runner uses Python's standard library, Git, Go, and the [OpenTelemetry Collector Builder (OCB)](https://opentelemetry.io/docs/collector/extend/ocb/). The source under test is a pinned commit of the [Contrib fork](https://github.com/oso-team/opentelemetry-collector-contrib).

## Current report data

[`docs/results.json`](docs/results.json) was produced by this repository's runner on 2026-09-28. It covers a default build and 41 detector selections at commit [`a5d5f6a7f795bbf53e45ef3a9a2291555c5c17b4`](https://github.com/oso-team/opentelemetry-collector-contrib/commit/a5d5f6a7f795bbf53e45ef3a9a2291555c5c17b4), on `darwin/arm64` with Go `1.26.4` and OCB `v0.161.0`. Its provenance is in the JSON. The [original report](https://oso-team.github.io/opentelemetry-collector-contrib/) preserves the earlier measurements at commit `136f367d26fd730fcfdad620be6387e57307c14c`.

The 42 Collector binaries were built and measured from a clean public checkout of the branch. The runner also recorded reachable module inventories, package counts, and portable OCB manifests. The default build measured 186 reachable modules and 108,223,826 binary bytes; the GCP-only build measured 76 reachable modules and 47,058,562 binary bytes.

The report is a standalone HTML file with embedded CSS, JavaScript, and a measured data snapshot. Open `docs/index.html` directly, or serve `docs/` over HTTP (for example, `python3 -m http.server 8000 --directory docs`) and open `http://localhost:8000`. GitHub Pages can publish the `docs/` directory from `main` after the repository owner enables Pages.

## Reproduce the experiment

Prerequisites: Python 3.10 or newer, Git, Go `1.26.4`, and released OCB `v0.161.0`. `experiment.json` pins the toolchain, public source commit, Collector component module versions, platform, and 42 build targets. The branch's core module dependencies use its exact public `v0.161.1` pseudo-version; the resource-detection processor is replaced with the local public checkout. This repository itself has no Python or JavaScript package dependencies.

1. Obtain a clean checkout of the pinned public source:

   ```sh
   git clone --branch rdp-module-split-v4 --single-branch https://github.com/oso-team/opentelemetry-collector-contrib.git /path/to/public-contrib
   git -C /path/to/public-contrib checkout --detach a5d5f6a7f795bbf53e45ef3a9a2291555c5c17b4
   ```

2. Install the pinned public OCB release. For example, run `go install go.opentelemetry.io/collector/cmd/builder@v0.161.0`. Check that `builder version` prints `ocb version v0.161.0` and `go version` prints `go1.26.4`.

3. Run a small comparison first:

   ```sh
   python3 tools/footprint.py --source /path/to/public-contrib --targets gcp,oraclecloud
   ```

   Use `--targets all` for the complete matrix. The baseline is always included. If the correct Go binary is not first on `PATH`, pass `--go /path/to/go`. If OCB is not named `builder`, pass `--builder /path/to/builder`. To measure source reachability without producing binaries, use `--no-build`.

4. Inspect `.runs/latest/results.json` and the portable builder manifests in `.runs/latest/evidence/`. The generated builds and raw local paths remain ignored under `.runs/`. The runner rejects a changed source commit, a dirty checkout, a mismatched tool version, or a failed build. It writes a result only after all selected targets succeed.

5. Validate a complete measured run, then explicitly update the Pages dataset and the HTML's offline snapshot:

   ```sh
   python3 tools/publish.py .runs/latest/results.json
   python3 tools/publish.py .runs/latest/results.json --write
   ```

   `publish.py` checks the source commit, build IDs, inventories, and binary measurements. Review the resulting diff before publishing.

## Measurement definitions

| Measure | Scope | How it is collected |
| --- | --- | --- |
| Reachable packages | Resource-detection processor | `go list -deps` under the selected build tags, excluding Go standard-library packages |
| Reachable modules | Resource-detection processor | Distinct module paths that own those packages |
| Packages per module | Resource-detection processor | Count of reachable packages owned by each module under that build's tags |
| Binary size | Complete minimal Collector | Byte size of the OCB-built executable with `-s -w` linker flags |
| Binary metadata | Complete minimal Collector | `go version -m` output, stored as portable evidence |

The runner builds the same receiver, processor, and exporter for every target. Only detector tags change. Compare results within one source revision, platform, Go toolchain, OCB version, and build configuration. The report's area labels group module paths by naming rules to aid browsing; they are not ownership or license classifications. Module reachability is not an SBOM, vulnerability result, license determination, or a runtime performance measurement. Binary size is not processor-only size.

The detector-selection implementation being measured is public. Its four initial commits [separate Kubernetes configuration types](https://github.com/oso-team/opentelemetry-collector-contrib/commit/653d733c1f), [move the GCP metadata helper](https://github.com/oso-team/opentelemetry-collector-contrib/commit/d76640ec42), [place detector registration behind build tags](https://github.com/oso-team/opentelemetry-collector-contrib/commit/a5fdf9cfca), and [keep detector configuration imports light](https://github.com/oso-team/opentelemetry-collector-contrib/commit/136f367d26). The pinned branch commit includes subsequent upstream merges and two more Azure detectors. Re-run the benchmark against a new pinned commit when the 0.162.0 core and Contrib releases are both available.

## Repository layout

| Path | Purpose |
| --- | --- |
| `experiment.json` | Pinned public source, build configuration, and target matrix |
| `tools/footprint.py` | Build and measurement runner |
| `tools/publish.py` | Publication validation and dataset update |
| `docs/` | Dependency-free interactive report and published result snapshot |
| `tests/` | Data-contract and publication checks |

## License and attribution

This repository is licensed under [Apache-2.0](LICENSE). OpenTelemetry Collector and Collector Contrib are separately maintained [Apache-2.0 projects](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/LICENSE). The historical measurements are attributed to the [original public report](https://oso-team.github.io/opentelemetry-collector-contrib/). This project is an independent experiment and is not an official OpenTelemetry distribution.
