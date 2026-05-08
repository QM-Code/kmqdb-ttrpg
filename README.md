# KMQDB TTRPG

This is a temporary repo until we figure out how to integrate items from kboecker.

## Local Sync

This local checkout is managed with `kbuild`. The GitHub connection is
configured in `.kbuild.json`.

Use `kbuild` from the repository root:

```bash
kbuild --git-sync "<message>"
```

Do not run `kbuild --git-sync` from a nested directory. It only syncs when the
current directory is the git worktree root.

## kboecker Agent Connection

The agent will run Codex on macOS and does not need `kbuild`. It only needs Git
and write access to `QM-Code/kmqdb-ttrpg`.

Use SSH if the Mac has a GitHub SSH key configured:

```bash
git clone git@github.com:QM-Code/kmqdb-ttrpg.git
cd kmqdb-ttrpg
```

Use HTTPS if SSH is not configured:

```bash
git clone https://github.com/QM-Code/kmqdb-ttrpg.git
cd kmqdb-ttrpg
```

Before starting work:

```bash
git status
git pull --ff-only origin main
```

After making changes:

```bash
git status
git add -A
git commit -m "<message>"
git push origin main
```

If Git identity is not configured on the Mac yet:

```bash
git config --global user.name "kboecker"
git config --global user.email "<github-email>"
```
