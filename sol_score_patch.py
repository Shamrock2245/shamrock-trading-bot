#!/usr/bin/env python3
"""Add Solana minimum score gate to gem_scanner.py"""

with open("scanner/gem_scanner.py") as f:
    content = f.read()

target = '            candidate.vol_trend_7d = "neutral"\n\n        return candidate'

replacement = '''            candidate.vol_trend_7d = "neutral"

        # -- FINAL GATE: Solana Meme Coin Quality Floor --
        # Solana meme coins need a HIGHER bar than EVM tokens.
        SOLANA_MIN_SCORE = 72.0
        if token.chain == "solana" and candidate.gem_score < SOLANA_MIN_SCORE:
            logger.info(
                f"⛔ SOLANA QUALITY GATE: {token.symbol} score={candidate.gem_score:.1f} "
                f"< {SOLANA_MIN_SCORE} Solana minimum. Skipping."
            )
            return None

        return candidate'''

if target in content:
    content = content.replace(target, replacement)
    with open("scanner/gem_scanner.py", "w") as f:
        f.write(content)
    print("OK - Solana score gate added")
else:
    if "SOLANA QUALITY GATE" in content:
        print("ALREADY APPLIED")
    else:
        print("ERROR - target not found")
