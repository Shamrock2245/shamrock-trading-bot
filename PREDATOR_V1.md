# Predator v1

**On `main`, PAPER ONLY.** Merged 2026-09-28 at Brendan's request to run in paper.
It is not a live-size unlock: `PAPER_MODE_LOCKED=true` / `MODE=paper` stay forced by CI.

Paper-first expansion hunter for Hyperliquid perps. Built off the
`hl_fills.jsonl` book (530 closes, WR 37%, PF 0.685, −$339, Jun 17–Jul 26 2026).

## The play

Stop blending 29 indicators across 150 names. Trade a short allowlist
only when the tape is expanding. Sit when it is chop. Hard-ban the names
that already wrecked the account.

## Gates (`core/predator_v1.py`)

Flag: `PREDATOR_V1_ENABLED` (code default off; `.env.example` + CI deploy set it `true`).

**Fail-closed:** when enabled, any import / regime / evaluation error in the
scanner path logs `[PREDATOR] ... fail-closed` and skips the entry.

1. Hard-ban (`HL_PERPS_HARD_BAN_COINS`) — TRB/GRASS/HMSTR and the rest of the bleed list.
2. Allowlist (`HL_PERPS_ALLOWLIST`) — AAVE/VVV/DYDX/MON/JUP and other names that printed.
3. Expansion only — `Choppy` is a skip, not half-size. Unknown regime fail-closed.
4. Toxic hours ET 08–13 skip (`PREDATOR_BLOCK_TOXIC_HOURS`).
5. Daily open cap (`PREDATOR_MAX_OPENS_PER_DAY`, default 6).

Wired into `HLPerpsScanner._execute_signal` after the long-only check.
When the flag is off the scanner is unchanged.

## Three-File Update Rule

Every `PREDATOR_*`, `HL_PERPS_ALLOWLIST`, `HL_PERPS_HARD_BAN_COINS` change needs:
1. code default (`core/predator_v1.py` + `core/hl_perps_scanner.py`)
2. `.env.example`
3. the deploy `sed` line in `.github/workflows/ci.yml`

`tests/test_predator_v1.py::test_three_file_rule_predator_vars` enforces it, and
`test_ci_deploy_keeps_paper_lock_and_moralis_off` guards the paper lock.

## UI

`dashboard/pages/12_🎮_Predator_Floor.py` — one arcade screen.
Regime billboard, heat, combo, ban hammer, last 20 sprites.

## What this is not

- Not parabolic. PF 0.68 does not become 3.0 because we added a page.
- Not a Moralis score pad. Pro sub is veto/wallet quality, not +12% on a blender.
- Not an LLM writing live `.env` after a red day.

## Promote rule

Paper until ≥50 closes, WR ≥50%, PF ≥1.30. Then discuss live. Not before.

## Fills review (2026-09-28, `output/hl_fills.jsonl`, 387 close orders / 530 close fills)

Defaults kept — the per-coin book agrees with them. Every coin with ≥5 closes
and negative net is on the hard-ban list; every allowlist name is net ≥ ~$0.
Marginal names to watch in paper: BTC (4 closes, −$1.46, PF 0.89), INJ
(10, −$0.02), LINK (5, +$0.32). Banned-but-flat names that could be
re-evaluated later: ETHFI (9, +$4.69, PF 1.35), CRV (11, +$1.01), LDO
(17, −$1.11, 65% WR), ZEC (3, −$0.76). Top printers: AAVE +$65, MON +$58,
TNSR +$53, VVV +$24, DYDX +$17, XMR +$14. Worst: TRB −$202, GRASS −$167,
SOL −$51, MET −$34, EIGEN −$26.
