# Install Upgrade Audit

Official page: https://martialgames.net/tools/upgrade-audit/

```bash
grok plugin marketplace add martialsystems/upgrade-audit
grok plugin install upgrade-audit --trust
```

Download `upgrade-audit-<ver>.zip` from GitHub Releases (the asset, not Source code zip).

```bash
chmod +x bin/upgrade-audit
export PATH="$PWD/bin:$PATH"
upgrade-audit configure --mode audit --kill none
upgrade-audit doctor
```

Need Python 3.9+, git, and `gh auth login`. Choose `--kill stall` if you want silent children killed after 8 minutes with no progress.

`gh` talks to GitHub as you. The runner does not upload repos to Martial Systems.
