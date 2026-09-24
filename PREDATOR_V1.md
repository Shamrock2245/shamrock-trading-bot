# Predator v1

**Branch only. Do not merge to `main` as a live-size unlock.**

Paper-first expansion hunter for Hyperliquid perps. Built off the
`hl_fills.jsonl` book (530 closes, WR 37%, PF 0.685, −$339, Jun 17–Jul 26 2026).

## The play

Stop blending 29 indicators across 150 names. Trade a short allowlist
only when the tape is expanding. Sit when it is chop. Hard-ban the names
that already wrecked the account.

## Gates (`core/predator_v1.py`)

Flag: `PREDATOR_V1_ENABLED` (off unless set).

1. Hard-ban (`HL_PERPS_HARD_BAN_COINS`) — TRB/GRASS/HMSTR and the rest of the bleed list.
2. Allowlist (`HL_PERPS_ALLOWLIST`) — AAVE/VVV/DYDX/MON/JUP and other names that printed.
3. Expansion only — `Choppy` is a skip, not half-size. Unknown regime fail-closed.
4. Toxic hours ET 08–13 skip (`PREDATOR_BLOCK_TOXIC_HOURS`).
5. Daily open cap (`PREDATOR_MAX_OPENS_PER_DAY`, default 6).

Wired into `HLPerpsScanner._execute_signal` after the long-only check.
When the flag is off the scanner is unchanged.

## UI

`dashboard/pages/12_🎮_Predator_Floor.py` — one arcade screen.
Regime billboard, heat, combo, ban hammer, last 20 sprites.

## What this is not

- Not parabolic. PF 0.68 does not become 3.0 because we added a page.
- Not a Moralis score pad. Pro sub is veto/wallet quality, not +12% on a blender.
- Not an LLM writing live `.env` after a red day.

## Promote rule

Paper until ≥50 closes, WR ≥50%, PF ≥1.30. Then discuss live. Not before.
