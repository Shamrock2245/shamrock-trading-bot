#!/bin/bash
# pre-tool.sh — Pre-tool hook for self-improving agent
# Loads relevant patterns into working memory before tool execution.
#
# Usage: bash pre-tool.sh "$TOOL_NAME" "$TOOL_INPUT"
# Designed for Claude Code hooks; reference implementation for other agents.

TOOL_NAME="${1:-}"
TOOL_INPUT="${2:-}"
SKILLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKING_DIR="$SKILLS_DIR/memory/working"
SEMANTIC_FILE="$SKILLS_DIR/memory/semantic-patterns.json"

# Ensure working directory exists
mkdir -p "$WORKING_DIR"

# Update current session with tool context
if [ -f "$WORKING_DIR/current_session.json" ]; then
    # Use python to safely update JSON (jq not always available)
    python3 -c "
import json, datetime

with open('$WORKING_DIR/current_session.json', 'r') as f:
    session = json.load(f)

session['skill_in_use'] = '$TOOL_NAME'
session['started_at'] = session.get('started_at') or datetime.datetime.utcnow().isoformat() + 'Z'

with open('$WORKING_DIR/current_session.json', 'w') as f:
    json.dump(session, f, indent=2)
" 2>/dev/null
fi

# For Bash/Write/Edit tools, check if a relevant pattern exists
if [[ "$TOOL_NAME" =~ ^(Bash|Write|Edit) ]]; then
    # Look for patterns related to files being modified
    if [ -f "$SEMANTIC_FILE" ]; then
        pattern_count=$(python3 -c "
import json
with open('$SEMANTIC_FILE') as f:
    data = json.load(f)
print(len(data.get('patterns', {})))
" 2>/dev/null || echo "0")

        if [ "$pattern_count" -gt "0" ]; then
            echo "[self-improving-agent] $pattern_count patterns loaded for context"
        fi
    fi
fi
