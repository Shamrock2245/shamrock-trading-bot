---
description: How to commit and push code changes to GitHub
---

# Commit and Push to GitHub

## Prerequisites
- Working directory: `/Users/brendan/Desktop/shamrock-trading-bot`
- Remote: `origin` → `https://github.com/Shamrock2245/shamrock-trading-bot.git`
- Branch: `main`

## Steps

### 1. Fix git permissions (if needed — macOS SIP can lock .git/logs)
// turbo
```bash
chmod -R u+rw .git/logs 2>/dev/null || true
```

### 2. Check what's changed
// turbo
```bash
git status --short
```

### 3. Stage the changed files
```bash
git add <file1> <file2> ...
```
Or to stage everything:
```bash
git add -A
```

### 4. Commit with a descriptive message
```bash
git commit -m "type: short description of changes"
```
Use conventional commit types: `fix:`, `feat:`, `refactor:`, `chore:`, `docs:`

### 5. Push to GitHub
```bash
git push origin main
```

## Fallback: GitHub API Push
If local git is completely broken (permissions, auth, etc.), use the GitHub MCP `push_files` tool:

```
mcp_github-mcp-server_push_files(
    owner="Shamrock2245",
    repo="shamrock-trading-bot",
    branch="main",
    message="commit message here",
    files=[
        {"path": "relative/path/to/file.py", "content": "<file content>"}
    ]
)
```

**Note:** This requires the GitHub token to have `Contents: Read and Write` permission on the repo. If you get "Permission Denied: Resource not accessible by personal access token", the user needs to update the token permissions at https://github.com/settings/tokens.
