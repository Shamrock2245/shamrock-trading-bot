#!/bin/bash
# post-bash.sh — Post-bash hook for self-improving agent
# Captures errors from bash commands for self-correction.
#
# Usage: bash post-bash.sh "$TOOL_OUTPUT" "$EXIT_CODE"
# Designed for Claude Code hooks; reference implementation for other agents.

TOOL_OUTPUT="${1:-}"
EXIT_CODE="${2:-0}"
SKILLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKING_DIR="$SKILLS_DIR/memory/working"

# Ensure working directory exists
mkdir -p "$WORKING_DIR"

# If non-zero exit code, capture error context
if [ "$EXIT_CODE" != "0" ]; then
    python3 -c "
import json, datetime

error_data = {
    'error_type': 'bash_nonzero_exit',
    'error_message': '''${TOOL_OUTPUT}'''[:500],
    'exit_code': int('$EXIT_CODE'),
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    'context': 'Captured by post-bash hook'
}

with open('$WORKING_DIR/last_error.json', 'w') as f:
    json.dump(error_data, f, indent=2)

print(f'[self-improving-agent] Error captured (exit code $EXIT_CODE)')
" 2>/dev/null
fi
