# Changelog

## 2026-10-16

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
