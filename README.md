# Upgrade Audit

<p align="right">
  <a href="https://ko-fi.com/martialgames"><img src="https://img.shields.io/badge/Donate-Ko--fi-ff5e5b?style=flat-square&logo=ko-fi&logoColor=white" alt="Donate on Ko-fi" /></a>
  &nbsp;
  <a href="https://martialgames.net/"><img src="https://img.shields.io/badge/Martial%20Games-site-1a3a2a?style=flat-square" alt="Martial Games" /></a>
  &nbsp;
  <a href="https://martialsys.net/"><img src="https://img.shields.io/badge/Martial%20Systems-site-1a3a2a?style=flat-square" alt="Martial Systems" /></a>
</p>

**Martial Systems LLC** product: a Grok plugin plus a local runner that inventories your GitHub repos, reviews shipped logic when a new Grok generation ships, writes a PDF, and then follows the mode you chose (`audit`, `fix`, or `pr`).

| | |
|--|--|
| **Publisher** | Martial Systems LLC |
| **Support** | martialsys@gmail.com · [Ko-fi](https://ko-fi.com/martialgames) |
| **Product page** | https://martialgames.net/tools/upgrade-audit/ |
| **License** | Proprietary personal use: [LICENSE](LICENSE), [Terms](docs/TERMS_OF_USE.md) |
| **Privacy** | We do not receive your repos. [Privacy](docs/PRIVACY.md) |

This GitHub repository is a **landing page and marketplace index**. Source is not published.

## Install the Grok plugin

```bash
grok plugin marketplace add martialsystems/upgrade-audit
grok plugin install upgrade-audit --trust
```

Then download **`upgrade-audit-1.0.0.zip`** from [Releases](https://github.com/martialsystems/upgrade-audit/releases). Do not use “Source code (zip)” and do not use Code → Download ZIP. Those archives are this landing page only.

```bash
unzip upgrade-audit-1.0.0.zip
cd upgrade-audit-1.0.0
chmod +x bin/upgrade-audit
export PATH="$PWD/bin:$PATH"
upgrade-audit configure --mode audit   # or fix | pr
upgrade-audit doctor
```

Need Python 3.9+, `git`, and `gh auth login` (`repo` scope).

## Modes (you choose)

| Mode | After the PDF |
|------|----------------|
| `audit` | Read-only. Issues and proposed fixes only. |
| `fix` | Apply confirmed findings on a branch. No PR, no merge. |
| `pr` | Same as fix, then open a GitHub PR. No merge. |

`/upgrade-audit --mode fix` overrides the saved choice for one run. If nothing is saved, Grok asks.

## New repositories

`upgrade-audit inventory --adopt` adds each new owned non-fork under your `gh` login. Forks are auto-excluded. Move a row to `excluded` if it is not a product.

## What this repo is not

It is not the runner source. If a zip has no `bin/upgrade-audit`, you downloaded the landing archive.
