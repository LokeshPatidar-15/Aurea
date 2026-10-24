import json
import subprocess
import sys
from pathlib import Path

NOTEBOOK_DIR = Path(__file__).parent.parent / "notebooks"
NOTEBOOK = NOTEBOOK_DIR / "aurea_eda.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.strip().splitlines(keepends=True),
    }


CELLS = [
    md("# Aurea: Phase 5 EDA\nCleaned 1h candles for BTCUSDT, XAUUSD (PAXGUSDT proxy) and EURUSD (EURUSDT proxy). "
       "Every number here comes from the same functions the pipeline uses, so the notebook cannot drift from the code."),
    code("import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path.cwd().parent))\n\n"
         "%matplotlib inline\nimport pandas as pd\n\nfrom analysis import eda\n\npd.set_option('display.width', 120)"),
    code("dfs = eda.load_all('1h')\npd.DataFrame({s: {'candles': len(d), 'first': d.index[0], 'last': d.index[-1], "
         "'filled': int(d['is_filled'].sum()), 'outliers': int(d['is_outlier'].sum())} for s, d in dfs.items()}).T"),
    md("## 1. Prices on one scale\nBTC, gold and EUR live on completely different scales, so we rebase each to 100 at the start."),
    code("eda.plot_rebased(dfs);"),
    md("## 2. Levels vs returns\nTwo trending series show a high *level* correlation even when they are unrelated. "
       "Returns remove the trend, so the return correlation is the honest relationship."),
    code("display(eda.levels_vs_returns_corr(dfs).round(3))\neda.plot_corr(dfs);"),
    md("## 3. Volatility by hour (UTC)\nMarkets are not equally active all day. Strategies and risk limits should know this."),
    code("eda.plot_hour(dfs);"),
    md("## 4. Volatility clustering\nThe direction of the next candle is almost unpredictable, but the *size* of moves is persistent."),
    code("eda.plot_acf(dfs['BTCUSDT']);"),
    md("## 5. Do liquidity sweeps carry information?\nForward 4-candle return in basis points. The t-statistic is divided by "
       "sqrt(4) of the sample size because neighbouring forward windows overlap. A value inside roughly +-2 means: no evidence yet."),
    code("for symbol, df in dfs.items():\n    print(symbol)\n    display(eda.sweep_forward_returns(df, horizon=4).round(2))"),
    md("## What we learned\nFill this in after running: which pairs are really correlated, which hours matter, and whether sweeps "
       "show any edge on their own. Phase 6 (ML) starts from these honest baselines."),
]


def main() -> None:
    NOTEBOOK_DIR.mkdir(exist_ok=True)
    notebook = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK.write_text(json.dumps(notebook, indent=1))
    print(f"notebook written: {NOTEBOOK}")

    cmd = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(NOTEBOOK)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("notebook executed: outputs and charts are saved inside it")
    else:
        print("notebook written but not executed (open it in Jupyter or VS Code and Run All).")
        print(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "")


if __name__ == "__main__":
    main()
