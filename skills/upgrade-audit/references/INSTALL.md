# Install Upgrade Audit

Official page: https://martialgames.net/tools/upgrade-audit/

The Grok plugin and the Python runner ship in the **same git tree**. A marketplace or `git clone` of https://github.com/martialsystems/upgrade-audit is enough. There is no required extra zip.

```bash
grok plugin marketplace add martialsystems/upgrade-audit
grok plugin install upgrade-audit --trust
```

Or clone the same repository and run from it:

```bash
git clone https://github.com/martialsystems/upgrade-audit
cd upgrade-audit
python3 -m pip install -r requirements.txt
chmod +x bin/upgrade-audit
export PATH="$PWD/bin:$PATH"
upgrade-audit configure --mode audit --kill none
upgrade-audit doctor
```

Need Python 3.9+, git, and `gh auth login`. Choose `--kill stall` if you want silent children killed after 8 minutes with no progress.

`gh` talks to GitHub as you. The runner does not upload repos to Martial Systems.

A versioned zip on GitHub Releases is an optional snapshot of this same tree.
