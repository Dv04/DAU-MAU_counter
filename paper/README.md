# Erasure-Compliant, Differentially Private Distinct Counting for CCTV Analytics (Paper)

**Author:** Dev Sanghvi, Rice University  
**File:** `paper.tex` (LaTeX, standalone)

This repo contains a publication-ready LaTeX paper describing an edge→cloud pipeline for **differentially private distinct counting** (DAU/MAU-style) with **deletion support** in CCTV analytics.

---

## Structure

- `paper.tex` — the complete paper (inline citations; references listed at end).
- `Makefile` — convenience targets for building/cleaning.
- `Placeholders.md` — list of tokens you must fill (also mirrored in Appendix A).
- `info.md` — extra notes and a finalization checklist.

Optional (add your assets):
- `figs/arch.pdf` — architecture diagram (if used).
- `figs/noise_accuracy.pdf`, `figs/sketch_vs_exact.pdf`, `figs/perf.pdf` — evaluation figures.
- `tables/delete_replay.tex` — deletion replay table.

---

## Build Instructions

### Quick build (recommended)
```bash
make
# produces paper.pdf
