# Placeholders — What to Fill and Where

Search and replace **all** tokens below across the repo (primarily `paper.tex`).

| Token                     | Meaning                             | Example            | Where                          |
| ------------------------- | ----------------------------------- | ------------------ | ------------------------------ |
| `{{PAPER_DATE}}`          | Draft date string                   | `October 2025`     | `paper.tex` title page         |
| `{{ACCESS_DATE}}`         | Date you accessed online docs       | `2025-10-10`       | References to DataSketches     |
| `{{MAU_WINDOW_DAYS}}`     | Rolling window length (days)        | `30`               | System/Implementation sections |
| `{{EPSILON_DAU}}`         | ε for DAU releases                  | `0.3`              | Abstract, Evaluation           |
| `{{EPSILON_MAU}}`         | ε for MAU releases                  | `0.5`              | Abstract, Evaluation           |
| `{{DELTA}}`               | δ parameter (if used)               | `1e-6`             | Evaluation/System text         |
| `{{ERROR_PCT}}`           | Overall relative error summary      | `2`                | Abstract                       |
| `{{THROUGHPUT}}`          | Ingestion throughput (events/s)     | `50000`            | Abstract, Evaluation           |
| `{{QUERY_LAT_MS}}`        | Query latency p99 (ms)              | `40`               | Evaluation                     |
| `{{EVAL_DAYS}}`           | Evaluation horizon (days)           | `60`               | Evaluation setup               |
| `{{N_USERS}}`             | Total unique subjects in sim        | `1000000`          | Evaluation setup               |
| `{{DAILY_ACTIVE}}`        | Avg. daily active subjects          | `85000`            | Evaluation setup               |
| `{{REPEAT_RATE}}`         | Day-to-day overlap (%)              | `70`               | Evaluation setup               |
| `{{DELETE_START}}`        | Day index/date when deletions begin | `Day 30`           | Evaluation                     |
| `{{DELETE_COUNT}}`        | # of subjects erased                | `5000`             | Evaluation                     |
| `{{DAU_MAE}}`             | Mean Absolute Error for DAU         | `130`              | Results                        |
| `{{DAU_REL_ERR}}`         | Relative error (%) for DAU          | `1.6`              | Results                        |
| `{{MAU_REL_ERR}}`         | Relative error (%) for MAU          | `0.8`              | Results                        |
| `{{THETA_K}}`             | Theta sketch size (k)               | `16384`            | Results                        |
| `{{THETA_RSE}}`           | Nominal RSE (%) for Theta           | `1.6`              | Results                        |
| `{{FIG_NOISE_ACCURACY}}`  | Label for noise accuracy figure     | `fig:noise-acc`    | Evaluation/Results             |
| `{{FIG_SKETCH_VS_EXACT}}` | Label for sketch vs exact figure    | `fig:sketch-exact` | Evaluation/Results             |
| `{{FIG_PERF}}`            | Label for performance figure        | `fig:perf`         | Evaluation/Results             |
| `{{TAB_DELETE}}`          | Label for deletion replay table     | `tab:delete`       | Evaluation/Results             |
| `{{ARCH_DIAGRAM_PATH}}`   | Optional arch diagram path          | `figs/arch.pdf`    | System section                 |

## How to Fill

1. Replace tokens with your values.
2. Add any figures to the `figs/` folder and reference them in `paper.tex` using standard LaTeX `\includegraphics`.
3. Ensure references in `thebibliography` have complete author/venue/year data.
4. Build with `make` and resolve warnings/errors.