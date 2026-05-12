"""
core/cro_agent.py — Adversarial Risk Officer (CRO)

Uses Grok to act as an adversarial risk officer. Before executing a high-conviction
trade, the CRO reviews the GemCandidate and ResearchReport to find reasons NOT to
take the trade (narrative flaws, correlated risks, "too good to be true" setups).

Fixed: Uses shared grok_client.py with correct Responses API format, global rate
limiting, and prompt caching via prompt_cache_key.
"""
import json
import logging
from typing import Optional
from data.providers.grok_client import call_grok
from data.models import GemCandidate

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — kept static for optimal prompt caching
# xAI caches identical system prompt prefixes server-side. Do NOT embed
# dynamic content here — all variable data goes in the user message.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the Chief Risk Officer (CRO) for an aggressive crypto trading bot.
Your job is to be highly adversarial and skeptical. You must review the provided trade candidate
and find every possible reason NOT to take the trade. Look for narrative flaws, correlated risks,
on-chain red flags, or "too good to be true" setups.

Given the token data, return ONLY valid JSON with these exact fields:
{"risk_score": <int 0-100>, "verdict": "<REJECT|PROCEED_WITH_CAUTION|APPROVE>", "key_risks": ["<risk1>", "<risk2>"], "narrative_flaw": "<description of why the narrative might fail>", "summary": "<one line summary>"}

Scoring guide for risk_score (higher = MORE risky):
- 0-20: Very low risk, solid setup
- 21-40: Low risk, standard crypto risks apply
- 41-60: Moderate risk, some concerns but manageable
- 61-80: High risk, major red flags, likely a trap
- 81-100: Extreme risk, almost certainly a scam or terrible setup

If risk_score > 70, verdict MUST be REJECT."""


def evaluate_trade(candidate: GemCandidate, report_summary: dict) -> Optional[dict]:
    """
    Evaluate a trade candidate using Grok as the CRO.

    Returns a dict with risk_score, verdict, key_risks, narrative_flaw, summary.
    Returns None if CRO is disabled, API key missing, or request fails.
    """
    try:
        from config import settings
        if not getattr(settings, "CRO_AGENT_ENABLED", True):
            return None
    except Exception:
        pass

    # All dynamic data goes in the user message (system prompt stays static for caching)
    context = f"""Token: {candidate.token.symbol} ({candidate.token.name})
Chain: {candidate.token.chain}
Age: {candidate.token.age_hours:.1f} hours
Liquidity: ${candidate.token.liquidity_usd:,.0f}
Volume 24h: ${candidate.token.volume_24h:,.0f}
Gem Score: {candidate.gem_score:.1f}/100

Report Summary:
{json.dumps(report_summary, indent=2)}

Analyze this candidate and provide your adversarial risk assessment."""

    logger.info(f"CRO Agent: Evaluating {candidate.token.symbol}...")

    result = call_grok(
        system_prompt=SYSTEM_PROMPT,
        user_message=context,
        cache_key="cro_agent",
        temperature=0.3,
        max_output_tokens=500,
        parse_json=True,
        timeout=15,
        module="cro_agent",
    )

    if result is None:
        logger.debug(f"CRO Agent: No result for {candidate.token.symbol}")
        return None

    logger.info(
        f"CRO Agent Verdict for {candidate.token.symbol}: "
        f"{result.get('verdict')} (Risk Score: {result.get('risk_score')})"
    )
    return result
