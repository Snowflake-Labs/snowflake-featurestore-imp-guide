# Guide diagrams (PDF + HTML)

Architecture and flow figures are defined as **Mermaid** in `scripts/build_guide_diagrams.py` (written to `sources/*.mmd` when you run that script), pre-rendered to **PNG** in `png/`, and embedded in chapters with `![](../_diagrams/png/<name>.png)` (or `../../_diagrams/png/` from nested appendices).

**Why:** In-book `{mermaid}` cells rely on headless Chrome during `quarto render --to pdf`, which often produces broken or missing graphics in LaTeX. Committed PNGs render the same in PDF and HTML.

## Regenerate after editing a diagram

From the **repository root** (requires Node.js for `npx`):

```bash
python3 scripts/build_guide_diagrams.py
```

Then commit both the updated `.mmd` (if you changed sources in `scripts/build_guide_diagrams.py`) and the regenerated `.png` files.
