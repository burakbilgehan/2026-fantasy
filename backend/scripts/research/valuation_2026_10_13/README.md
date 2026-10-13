# Valuation model research, 2026-10-13

Scripts behind `docs/modules/valuation-models-research.md`. Research code, not part of the app: no tests, numpy only.
Run from `backend/`: `uv run python scripts/research/valuation_2026_10_13/mwv.py` (writes `mwv.npy` next to the scripts; the other
scripts read it). Order: `sanity.py` (Lloyd calibration check), `mwv.py` (empirical H2H value, 4 seasons), `evalmodels.py`,
`tournament.py [draws] [--oracle]`, `fitweights.py`, `puntctx2.py`, `puntweights.py`, `preseason.py`, `projsim.py`,
`durant_h2h.py`, `teamfit2.py`, `progression.py`, `movers.py`, `volscale.py`. Outputs of the 2026-10-13 run: `out_*.txt`
in `data/research/valuation-2026-10-13/` (local, not in git).
