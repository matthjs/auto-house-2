# Welcome! 🚗🏠

Do you like to spend time looking for housing? No, neither do I!

Well, what about getting your own housing agent! An agent can be that for you: it crawls the housing sites, decides which offers actually fit you, and writes a personal message to each landlord.

> **Note:** this is a fork of [auto-house](https://github.com/MichalTesnar/auto-house) by [Michal Tesnar](https://github.com/MichalTesnar), who wrote the original scrapers and idea, with contributions from Ryan Slocum. This fork adds the agent loop (fit check, self-review), more LLM providers, a CLI and tests. If `auto-house` has helped you, consider starring the original repository as well.

# How it works

You talk to a coding agent (Claude Code or Codex) and it does the searching with you:

1. **Search.** It runs the tool, which finds new listings on the housing sites. This contacts nobody.
2. **Judge.** It scores each listing against your budget, place and deal breakers, flags anything that looks like a scam, and shows you a ranked table.
3. **Draft.** For the ones you pick, it writes a short message in the listing's language, using only facts about you (and your flatmates, if you search together), and checks it against a review list.
4. **You send.** You approve or tweak each message. For website forms you paste it in yourself (the sites have bot checks); for wohnen.ethz.ch it can email the landlord after your OK. Then it records the listing as sent.

Every listing gets a record in `data/<search>/<site>/` with its status (`found`, `skipped`, `drafted`, `needs_review`, `failed`, `rejected`, `sent`), the URL, the text, the fit and the message. A listing is never contacted twice, even if several people share a search.

There's also a **batch mode** without the chat: `make me-have-a-house SITE=wgzimmer` lets an API model (DeepSeek, Claude or OpenAI) judge and draft every new listing in one cheap run, for example as a daily job. You review the drafts later.

**Dry run is on by default.** Nothing is sent, and no listing is marked as sent or rejected, unless the command gets `dry_run=false`. The agent only adds that after your OK for that one listing. (Searching and drafting still save their results in `data/`, so nothing is lost or paid for twice.)

# Principles of usage

Please do not overuse this! The agent never responds to the same listing twice. Please do not modify it to send messages repeatedly.

Please use this moderately, and never try to get around a site's bot checks.

# Integrated websites

| Site | `site=` | Login needed | How landlords are contacted | Status (November 2026) |
|---|---|---|---|---|
| [WGZimmer.ch](https://www.wgzimmer.ch/home.html) | `wgzimmer` | No | You paste the message into the site's form | Works (plain HTTP, no browser) |
| [Flatfox.ch](https://flatfox.ch/c/en/) | `flatfox` | Yes | Site form | Not verified against the current site |
| [Zimmer- und Wohnungsvermittlung Universität/ETH Zürich](https://www.wohnen.ethz.ch/) | `wohnen_ethz` | Yes | Email from your Gmail, after your OK | Site shows "Service not available" |

wgzimmer.ch lists single rooms in shared flats, so it suits people searching alone. Groups are better off on Flatfox.

# Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (and Google Chrome for Flatfox and wohnen.ethz.ch).
2. `uv sync`, then `cp .env.example .env`
3. Open [Claude Code](https://claude.com/claude-code) or [Codex](https://developers.openai.com/codex) in this folder and run **`/setup`** (Claude Code) or say **"set up auto-house"** (Codex). It checks the install, asks whether you search alone or together, your budget and what you're looking for, writes the config files, and explains the optional API key for batch mode.
4. Fill in `.env` with what it tells you. For wgzimmer.ch in chat mode that's nothing at all; every variable is explained in [.env.example](.env.example).

Then say **"find me housing on wgzimmer"** (the `find-housing` skill).

**Without a coding agent:** `make new-search SEARCH=<you>` copies the example files to `conf/person/<you>.yaml` and `conf/search/<you>.yaml`; fill them in by hand, add an API key to `.env`, and use batch mode.

## Where things live

| What | Where | In git? |
|---|---|---|
| Who each person is | `conf/person/<name>.yaml` | No |
| What a search is looking for, and who is in it | `conf/search/<name>.yaml` | No |
| Passwords and API keys | `.env` | No |
| What happened to each listing | `data/<search>/` | No |
| Settings and their defaults | [conf/config.yaml](conf/config.yaml) | Yes |

Only the `example.yaml` files are tracked. Searching together: one `conf/person/` file per person, and one search that lists them as `members` with one `contact`. The contact's accounts are used and landlords reply to them.

**Coming from the original auto-house (`secret/<you>/`)?** Run `make migrate SEARCH=<you>`. It turns your two JSON files into a person file and a one-person search, and copies your listing records to `data/<you>/` so nobody gets contacted twice. It deletes and overwrites nothing, and it doesn't touch passwords: it lists which `site_credentials.json` field goes into which `.env` variable. Once `make status SEARCH=<you>` looks right, delete `secret/<you>/`.

# Using the tool directly

The agent calls these commands, but you can too. Configuration is [Hydra](https://hydra.cc/), so any setting can be changed on the command line.

```bash
uv run python main.py search=<name> site=wgzimmer command=search    # new listings as JSON
uv run python main.py search=<name> command=status                  # every listing so far
uv run python main.py search=<name> site=wgzimmer command=show listing=<id>
uv run python main.py search=<name> site=wgzimmer command=mark listing=<id> decision=sent message_file=msg.md dry_run=false
uv run python main.py search=<name> site=wohnen_ethz command=send listing=<id> message_file=msg.md   # shows the email; add dry_run=false to send
uv run python main.py search=<name> site=wgzimmer command=run       # batch mode (drafts only)
uv run python main.py search=<name> site=wgzimmer --cfg job         # print the final config
```

A message file has an optional `Subject: ...` first line, then the message. Set `AUTO_HOUSE_SEARCH` in `.env` to leave out `search=`. Make shortcuts: `make search`, `make status`, `make me-have-a-house` (all take `SEARCH=` and `SITE=`).

## Batch mode and API models

| `llm=` | Default model | API key in `.env` |
|---|---|---|
| `deepseek` | `deepseek-flash` | `DEEPSEEK_API_KEY` ([get one](https://platform.deepseek.com/)) |
| `claude` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-6-luna` | `OPENAI_API_KEY` |

Without `llm=`, the first provider whose key is set is used (in the order above). Pick another model with `llm.model=...`. Check a key with one small paid call: `uv run python main.py search=<name> command=check-llm`.

Batch mode uses the instructions in [prompts/](prompts/): `evaluate.md` (fit rubric), `draft.md` (how to write) and `review.md` (the checklist). The `find-housing` skill uses the same files, so editing them changes both.

# Development

```bash
make test      # offline tests: no network, no API keys, no personal data needed
make format    # ruff format + autofix lint
make check     # what CI runs
```

Coding agents should read [AGENTS.md](AGENTS.md) first. The skills live in [.agents/skills/](.agents/skills/) (read by Codex; `.claude/skills` links there for Claude Code). The `add-site` skill walks through adding a new website.

Please open an issue if anything comes up, or make a pull request if you want to add a feature.
