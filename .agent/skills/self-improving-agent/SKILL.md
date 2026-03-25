---
name: self-improving-agent
description: Universal self-improvement system that learns from all coding experiences on the Shamrock Trading Bot. Implements multi-memory architecture (semantic + episodic + working), self-correction, and evolution markers for traceable skill updates.
---

# Self-Improving Agent

## Overview

This skill implements a complete feedback loop for learning from every interaction with the Shamrock Trading Bot codebase. It maintains:

- **Semantic Memory** (`memory/semantic-patterns.json`) — Abstract, reusable patterns and rules
- **Episodic Memory** (`memory/episodic/`) — Specific past experiences and debugging sessions
- **Working Memory** (`memory/working/`) — Current session context

## When This Activates

### Automatic Triggers
- After any bug fix or deployment
- After any trade execution failure is resolved
- After any scoring regression is identified and fixed
- When a pattern repeats 3+ times across sessions

### Manual Triggers
- User says "self-improve", "learn from this", "update your memory"
- User asks to analyze recent experiences or summarize lessons learned

## Trading Bot Domain Categories

| Category | Covers | Key Files |
|----------|--------|-----------|
| `trade_execution` | Executor logic, Solana executor, wallet routing, slippage | `core/executor.py`, `core/solana_executor.py`, `core/wallet_router.py` |
| `scoring_engine` | Signal engine, gem scanner, indicator fallbacks, composite scoring | `core/signal_engine.py`, `scanner/gem_scanner.py` |
| `deployment` | Docker builds, Hetzner VPS, `.env` provisioning, `clasp` deployments | `Dockerfile`, `docker-compose.yml`, `.env` |
| `guardrails` | Offensive/defensive guardrail interactions, position sizing, risk | `core/offensive_guardrails.py`, `core/risk.py`, `core/safety.py` |
| `data_pipeline` | Moralis API, safety checks, scraper integration, indicators | `data/providers/`, `core/fib_hunter.py` |
| `position_mgmt` | Position monitor, trailing stops, pyramiding, TP/SL logic | `core/position_monitor.py`, `core/moonshot_allocator.py` |
| `manus_integration` | Reviewing/merging Manus AI changes, import verification | Any file Manus touches |

## The Self-Improvement Loop

```
Skill Event → Extract Experience → Abstract Pattern → Update Skill
     │               │                    │                │
     ▼               ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                  MULTI-MEMORY SYSTEM                        │
├───────────────────┬──────────────────┬──────────────────────┤
│  Semantic Memory  │ Episodic Memory  │  Working Memory      │
│ (Patterns/Rules)  │ (Experiences)    │  (Current Session)   │
│ memory/semantic/  │ memory/episodic/ │  memory/working/     │
└───────────────────┴──────────────────┴──────────────────────┘
                          │
              ┌───────────┴────────────┐
              │     FEEDBACK LOOP      │
              │ Outcome → Confidence   │
              │ Update → Pattern Adapt │
              └────────────────────────┘
```

## Self-Improvement Process

### Phase 1: Experience Extraction

After any significant interaction (bug fix, deployment, feature), extract:

```yaml
What happened:
  skill_used: {which skill/area}
  task: {what was being done}
  outcome: {success|partial|failure}
Key Insights:
  what_went_well: [what worked]
  what_went_wrong: [what didn't work]
  root_cause: {underlying issue if applicable}
  files_modified: [list of files changed]
User Feedback:
  rating: {1-10 if provided}
  comments: {specific feedback}
```

### Phase 2: Pattern Abstraction

Convert experiences to reusable patterns:

```
If experience_repeats 3+ times:
  → pattern_level: critical
  → Add to "Critical Mistakes" or "Golden Rules"

If solution_was_effective:
  → pattern_level: best_practice
  → Add to semantic patterns with high confidence

If outcome == failure:
  → pattern_level: anti_pattern
  → Add to "What to Avoid" with root cause
```

### Phase 3: Skill Updates

Update semantic patterns with evolution markers:

```markdown
<!-- Evolution: 2026-03-25 | source: ep-2026-03-25-001 | category: scoring_engine -->
## Pattern Added (2026-03-25)
**Pattern**: Indicator fallback values must be neutral (50), never zero
**Source**: Episode ep-2026-03-25-001
**Confidence**: 0.95
```

### Phase 4: Memory Consolidation

1. Update semantic memory (`memory/semantic-patterns.json`)
2. Store episodic memory (`memory/episodic/YYYY-MM-DD-{topic}.json`)
3. Update pattern confidence based on applications/feedback
4. Prune outdated patterns (low confidence, no recent applications)

## Self-Correction

Triggered when:
- A suggested fix causes a new error
- Tests fail after following a pattern
- User reports incorrect guidance

**Process:**
1. Capture error context in `memory/working/last_error.json`
2. Identify which pattern/guidance was followed
3. Determine: was guidance incorrect, misinterpreted, or incomplete?
4. Update pattern with correction marker
5. Validate the corrected guidance

```markdown
<!-- Correction: 2026-03-25 | was: "use zero fallback" | reason: zeroed out composite score -->
## Self-Correction: Indicator Fallbacks
**Issue**: Using 0 as fallback for missing indicators zeroed out the weighted average
**Fix**: Use neutral value (50) as fallback — represents "no data, assume average"
**Pattern**: indicator_neutral_fallback
```

## Evolution Priority Matrix

| Priority | Trigger | Action |
|----------|---------|--------|
| 🔴 Critical | Bug caused trade loss or system crash | Immediate pattern update, high confidence |
| 🟠 High | Deployment failure, regression | Update within session |
| 🟡 Medium | Repeated inconvenience, 3+ occurrences | Schedule pattern extraction |
| 🟢 Low | Style preference, minor optimization | Note for batch consolidation |

## Best Practices

### DO
- ✅ Learn from EVERY debugging session and deployment
- ✅ Extract patterns at the right abstraction level (not too specific, not too vague)
- ✅ Update multiple related categories when a cross-cutting pattern emerges
- ✅ Track confidence scores and application counts
- ✅ Use evolution/correction markers for full traceability
- ✅ Bootstrap with real learnings, not theoretical patterns
- ✅ Cross-reference episodic memories when encountering similar issues

### DON'T
- ❌ Over-generalize from a single incident
- ❌ Update patterns without confidence tracking
- ❌ Ignore negative outcomes — those are the most valuable learnings
- ❌ Create contradictory patterns (resolve conflicts explicitly)
- ❌ Store sensitive data (API keys, wallet keys) in memory files
- ❌ Let memory files grow unbounded — consolidate and prune regularly

## References

- [SimpleMem: Efficient Lifelong Memory for LLM Agents](https://arxiv.org/html/2601.02553v1)
- [Multi-Memory Survey](https://dl.acm.org/doi/10.1145/3748302)
- [Lifelong Learning of LLM Agents](https://arxiv.org/html/2501.07278v1)
- [Original Skill](https://skills.sh/charon-fan/agent-playbook/self-improving-agent)
