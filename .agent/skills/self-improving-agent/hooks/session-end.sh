#!/bin/bash
# session-end.sh — Session end hook for self-improving agent
# Triggers experience extraction and pattern consolidation.
#
# Usage: bash session-end.sh
# Designed for Claude Code hooks; reference implementation for other agents.

SKILLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKING_DIR="$SKILLS_DIR/memory/working"

# Ensure working directory exists
mkdir -p "$WORKING_DIR"

# Write session end marker
python3 -c "
import json, datetime

session_end = {
    'ended_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'summary': 'Session ended — consolidation pending'
}

# Try to read current session for context
try:
    with open('$WORKING_DIR/current_session.json', 'r') as f:
        current = json.load(f)
    session_end['session_id'] = current.get('session_id')
    session_end['files_modified'] = current.get('files_modified', [])
    session_end['patterns_referenced'] = current.get('patterns_referenced', [])
except:
    pass

with open('$WORKING_DIR/session_end.json', 'w') as f:
    json.dump(session_end, f, indent=2)

# Reset current session
empty_session = {
    'session_id': None,
    'started_at': None,
    'skill_in_use': None,
    'task_description': None,
    'files_modified': [],
    'patterns_referenced': [],
    'notes': []
}

with open('$WORKING_DIR/current_session.json', 'w') as f:
    json.dump(empty_session, f, indent=2)

print('[self-improving-agent] Session ended, working memory cleared')
" 2>/dev/null
