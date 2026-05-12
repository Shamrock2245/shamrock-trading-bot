"""
core/cro_agent.py — Adversarial Risk Officer (CRO)
Uses Grok to act as an adversarial risk officer. Before executing a high-conviction
trade, the CRO reviews the GemCandidate and ResearchReport to find reasons NOT to
take the trade (narrative flaws, correlated risks, "too good to be true" setups).
"""
import json
import logging
import os
import time
from typing import Optional
from data.http_session import get_session
from data.models import GemCandidate

logger = logging.getLogger(__name__)

GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"
GROK_MODEL = "grok-4-1-fast-non-reasoning"

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

If risk_score > 70, verdict MUST be REJECT.
"""

def _get_api_key() -> str:
    try:
        from config import settings
        key = getattr(settings, "GROK_API_KEY", "")
        if key:
            return key
    except ImportError:
        pass
    return os.getenv("GROK_API_KEY", "")

def evaluate_trade(candidate: GemCandidate, report_summary: dict) -> Optional[dict]:
    try:
        from config import settings
        if not getattr(settings, "CRO_AGENT_ENABLED", True):
            return None
    except Exception:
        pass
    """
    Evaluate a trade candidate using Grok as the CRO.
    Returns a dict with risk_score, verdict, key_risks, etc.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("CRO Agent: GROK_API_KEY not found. Skipping CRO evaluation.")
        return None

    session = get_session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Build the context for Grok
    context = f"""
Token: {candidate.token.symbol} ({candidate.token.name})
Chain: {candidate.token.chain}
Age: {candidate.token.age_hours:.1f} hours
Liquidity: ${candidate.token.liquidity_usd:,.0f}
Volume 24h: ${candidate.token.volume_24h:,.0f}
Gem Score: {candidate.gem_score:.1f}/100

Report Summary:
{json.dumps(report_summary, indent=2)}

Analyze this candidate and provide your adversarial risk assessment.
"""

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info(f"CRO Agent: Evaluating {candidate.token.symbol}...")
        resp = session.post(GROK_RESPONSES_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        logger.info(f"CRO Agent Verdict for {candidate.token.symbol}: {result.get('verdict')} (Risk Score: {result.get('risk_score')})")
        return result
        
    except Exception as e:
        logger.error(f"CRO Agent: Failed to evaluate {candidate.token.symbol}: {e}")
        return None
