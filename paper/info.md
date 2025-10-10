# Info / Extra Notes

This file collects anything that didn’t fit neatly into the LaTeX or README.

## Repo Contents Recap
- `paper.tex` — full paper (LaTeX).
- `README.md` — how to build and where to insert figures/data.
- `Placeholders.md` — all tokens to fill before submission.
- `Makefile` — quick build/clean.

## Finalization Checklist
- [ ] Fill **all placeholders** (see `Placeholders.md` and Appendix A).
- [ ] Insert figures and tables or remove their references:
  - `{{ARCH_DIAGRAM_PATH}}` for architecture (optional)
  - `{{FIG_NOISE_ACCURACY}}`, `{{FIG_SKETCH_VS_EXACT}}`, `{{FIG_PERF}}`, `{{TAB_DELETE}}`
- [ ] Replace any placeholder author labels in references (e.g., “(Authors)”) with actual bibliographic data.
- [ ] Spell-check and proofread; ensure consistent terminology (Theta vs HLL++; DAU/MAU capitalization).
- [ ] If targeting ACM/IEEE, switch to their class (`acmart`/`IEEEtran`) and re-check formatting.
- [ ] Rebuild PDF (`make`) and fix warnings.
- [ ] (Optional) Add a `figs/` directory and a `tables/` directory to keep assets tidy.

## Suggestions for Figures/Tables (Templates)
- **Architecture (edge→cloud)**:
  - A simple box/arrow figure: Camera/NVR (hash+Theta per day) → Gateway (unions + A-not-B) → Cloud (DP release + ledger).
- **Noise Accuracy**:
  - Time series of true vs noisy DAU for 14 days; bar of MAE vs ε.
- **Sketch vs Exact**:
  - Scatterplot (exact vs sketch) with y=x diagonal; error bars by k.
- **Performance**:
  - Throughput vs batch size; latency CDF for queries.
- **Deletion Replay**:
  - Table: pre-/post- MAU (true and DP) and expected delta (± DP).

## Notes on References
- The `thebibliography` section is inline for simplicity. If your venue mandates BibTeX:
  1. Convert entries to a `.bib` file,
  2. Replace the inline section with `\bibliographystyle{abbrvnat}` and `\bibliography{refs}`,
  3. Update the build steps.

## Ethics/Compliance Hints
- Add a sentence clarifying evaluation used synthetic or fully anonymized data.
- If later using internal CCTV telemetry, prepare DPIA/IRB notes and consent/notice mechanisms.

## Future Enhancements (if you have time)
- Replace Laplace with Gaussian + RDP accounting for tighter composition.
- Integrate tree-aggregation for smoother continual releases.
- Include a brief comparison with Privid/VideoDP to position the contribution.

