# vendor/ — Vendored Dependencies

This directory contains Python packages that cannot be installed via PyPI
due to Python version constraints or build environment limitations.

---

## pandas-ta

**Status:** Vendored copy of `pandas-ta 0.4.67b0` (Python 3.12+ syntax — incompatible with 3.11)

**Why vendored:** The PyPI package requires Python ≥ 3.12. The GitHub development
branch uses f-string nested quotes (`f"..."` inside `f"..."`) that are a Python 3.12
syntax feature, causing `SyntaxError` on Python 3.11.

**Current approach:** The bot uses `strategies/indicators.py` which has full manual
fallback implementations of all required indicators (EMA, RSI, MACD, Bollinger Bands,
ADX, Stochastic RSI, VWAP, OBV). These are mathematically equivalent to pandas-ta and
tested against the same OHLCV data.

**To enable pandas-ta when running Python 3.12+:**
```bash
pip install pandas-ta  # Works on Python 3.12+
```

**Dockerfile fix for Python 3.12:**
```dockerfile
FROM python:3.12-slim
# ... rest of Dockerfile
RUN pip install pandas-ta  # Now works
```

**Manual fallback performance:** The manual implementations in `strategies/indicators.py`
are production-ready and have been validated against pandas-ta output. No functionality
is lost by using the fallback path.

---

## Adding New Vendored Packages

If you need to vendor a package:
1. Download the wheel: `pip download <package> --no-deps -d /tmp/wheels/`
2. Unzip: `unzip /tmp/wheels/<package>.whl -d vendor/<package_name>/`
3. Fix any version-check imports in `__init__.py`
4. Test: `PYTHONPATH=vendor python -c "import <package_name>"`
5. Add to `.gitignore` exclusions if needed (large packages)
