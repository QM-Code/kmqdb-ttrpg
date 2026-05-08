# KMQDB TTRPG

This is a temporary repo until we figure out how to integrate items from kboecker.

## GitHub Sync

This repo is managed with `kbuild`. The GitHub connection is configured in
`.kbuild.json`.

Use `kbuild` from the repository root:

```bash
kbuild --git-sync "<message>"
```

Do not run `kbuild --git-sync` from a nested directory. It only syncs when the
current directory is the git worktree root.

## kboecker Agent Connection

The agent needs write access to `QM-Code/kmqdb-ttrpg` and a non-interactive SSH
key that GitHub accepts.

Fresh checkout:

```bash
git clone git@github.com:QM-Code/kmqdb-ttrpg.git
cd kmqdb-ttrpg
```

Verify the connection:

```bash
ssh -o BatchMode=yes -T git@github.com
git ls-remote git@github.com:QM-Code/kmqdb-ttrpg.git
```

After making changes, publish them through `kbuild`:

```bash
kbuild --git-sync "<message>"
```
