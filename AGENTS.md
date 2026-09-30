# Repository guidance

This repository documents reproducible OpenTelemetry Collector build footprint experiments. Keep generated binaries, local paths, and credentials out of Git.

Keep source revisions, tool versions, build settings, and result provenance explicit. Compare module reachability and binary size within the same platform and build configuration. Label historical and partial results accurately.

Use Python and browser standard libraries for the runner and report unless a new dependency is necessary. Before adding a dependency, verify its exact version and license under the applicable third-party review process. Preserve upstream copyright and SPDX notices when reusing source.

Run the standard-library tests and publication validator for changes to measurements, data contracts, or report output. Maintain `CHANGELOG.md` with meaningful repository changes.
