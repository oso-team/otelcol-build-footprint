# Changelog

## 2026-10-29

- Refresh all 41 matched detector selections and both all-detector baselines; display per-binary inspection evidence and credit merged AWS/Kubernetes fixes to upstream main. Preserve the previous interactive report in an October 15 archive.

- Verify every measured binary with the components command, embedded build tags and implementation/stub file selection; additionally check the PR runtime detector inventory exactly. Reject publication when required inspection evidence is missing or fails.
- Pin the refreshed experiment to current upstream and PR commits, OCB/Core 0.164.0, Core stable 1.70.0 and Go 1.27.2; retain the previous input manifests.

## 2026-10-19

- Add a detector selector beside the three-way comparison, synchronized with the hero grid and shared URL.
- Label the Compare Builds default baseline and keep its bar visible while scrolling through the chart.

## 2026-10-16

- Darken the removed portions of comparison bars to improve contrast against the page background.

- Remove the removed-segment outline so adjacent bar colors meet without a seam stroke.

- Remove the disconnected zero-axis label and make retained/removed bar segments meet at a straight seam.

- Restore Compare Builds with a shared upstream baseline, paired bars for all 41 selections, filters, module/binary measures, and a table view.
- Restore hover invitations and categorized red/green module diffs with selectable baselines, package details, exact reproduction inputs, copyable tags, and shareable inspection URLs.
- Preserve the original external report and all measurement data unchanged.

## 2026-10-15

- Lead the homepage and comparison with pinned upstream-main versus PR measurements; preserve the September report at historical.html.
- Restore module hover details, a selector above the hero grid, and its dropdown prompt, with keyboard and touch access.
- Explain configuration dependency fixes separately from build-tag selection syntax, and show small binary increases in bytes.

- Reuse the original report design for the matched comparison, with dark mode, module squares, shared filter URLs and the simplified mechanism explanation.

- Add pinned manifests and a guarded runner for the matched unified-detector-tag comparison.
- Validate source, toolchain, module and binary provenance before exporting cross-strategy results.
- Add a standalone three-way comparison with module inspection and an old-implementation control.

## 2026-10-14

- Publish the standalone report through GitHub Pages from `main`/`docs`.

## 2026-09-29

- Focus repository guidance and publication checks on reproducible results.
- Restore the original report's presentation and interactions, using the measured public dataset and public reproduction links.
- Keep the standalone HTML's embedded snapshot in sync when publishing a new run.
- Simplify module tooltips and clarify binary size reduction; keep KPI info icons circular.

## 2026-09-28

- Add a public, pinned resource-detector build matrix and measurement runner.
- Add a dependency-free interactive report with 42 builds measured from the current public proposal branch.
- Add publication validation and reproducibility guidance.
- Restore a selectable module grid and grouped module diff, with measured package counts per module.
