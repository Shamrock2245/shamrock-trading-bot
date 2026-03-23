---
description: How to commit and push code changes to GitHub
---
// turbo-all

## Steps

1. Stage the changed files:
```bash
git add -A
```

2. Check what's staged:
```bash
git status --short
```

3. Commit with a descriptive message:
```bash
git commit -m "<descriptive commit message>"
```
> Use conventional commit format: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, etc.

4. Push to the remote `main` branch:
```bash
git push origin main
```

## Notes
- Always review `git status` before committing to avoid unintended files.
- If there are untracked files that shouldn't be committed, add them to `.gitignore` first.
- If push fails due to remote changes, run `git pull --rebase origin main` first, then push again.
