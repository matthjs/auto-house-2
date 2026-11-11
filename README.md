# Welcome! 🚗🏠

Do you like to spend time looking for housing? No, neither do I!

Well, what about getting your own housing agent! An LLM can be that for you: it crawls the housing sites, decides which offers actually fit you, and writes a personal message to each landlord.

> **Note:** this is a fork of [auto-house](https://github.com/MichalTesnar/auto-house) by [Michal Tesnar](https://github.com/MichalTesnar), who wrote the original scrapers and idea, with contributions from Ryan Slocum. This fork adds the agent loop (fit check, self-review), more LLM providers, a CLI and tests. If `auto-house` has helped you, consider starring the original repository as well.

# How it works

For every new listing on a site, the agent:

1. **Checks the fit.** It scores the listing from 0 to 100 against your budget, place, deal breakers and description, and flags anything that looks like a scam. Listings below the threshold are skipped and never looked at again.
2. **Drafts a message.** It first works out who will read it (a flatshare, a private landlord, an agency) and what they ask for. Then it writes a short message in the listing's language, using only facts from your description.
3. **Reviews the draft.** Fixed rules catch placeholders and bad length, and the LLM checks language, facts and tone. A failing draft is rewritten once with the feedback.
4. **Sends, if you allow it.** By default nothing is sent. See [Modes](#modes).

Every listing gets a record in `data/<you>/<site>/` with its status (`skipped`, `drafted`, `needs_review`, `failed`, `rejected`, `sent`), the URL, the fit score, the draft and timestamps. A listing is never contacted twice, and it only counts as `sent` once the site or mail server accepted the message.

# Principles of usage

Please do not overuse this! The agent never responds to the same listing twice. Please do not modify it to send messages repeatedly.

Please use this moderately, and never try to get around a site's bot checks.

# Integrated websites

| Site | `site=` | How landlords are contacted | Status (November 2026) |
|---|---|---|---|
| [Zimmer- und Wohnungsvermittlung Universität/ETH Zürich](https://www.wohnen.ethz.ch/) | `wohnen_ethz` | Email from your Gmail | Site shows "Service not available" |
| [WGZimmer.ch](https://www.wgzimmer.ch/home.html) | `wgzimmer` | Contact form on the site | Site was redesigned; scraper needs an update. Its contact form now has a bot check, so sending can't be automated |
| [Flatfox.ch](https://flatfox.ch/c/en/) | `flatfox` | Contact form on the site | Not verified against the current site |

# Setup

Three things, each in its own place. All three are git-ignored, except the examples.

| What | Where |
|---|---|
| Who you are and what you're looking for | `conf/profile/<you>.yaml` |
| Passwords and API keys | `.env` |
| What the agent did per listing | `data/<you>/` (written by the tool) |

## Install

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Google Chrome.
2. `uv sync` (installs Python 3.10+ and all dependencies into `.venv/`).

## Your profile

1. `make new-profile PROFILE=<you>` copies [conf/profile/example.yaml](conf/profile/example.yaml) to `conf/profile/<you>.yaml`, and creates `.env` from [.env.example](.env.example) if you don't have one yet.
2. Fill in `conf/profile/<you>.yaml`:
   - `description`: who you are. The agent only uses facts from here, so the more you put in, the better the messages.
   - `preferences.budget_upper_bound`: maximum rent in CHF (required).
   - `preferences.place`: city for Flatfox and wohnen.ethz.ch, for example `Zürich`.
   - `preferences.place_wg_zimmer`: the region value from wgzimmer.ch's search form.
   - `preferences.move_in_date`, `nice_to_haves`, `deal_breakers`: optional, used by the fit check.
3. Fill in `.env` for what you use (every variable is listed there, with comments):
   - `DEEPSEEK_API_KEY` (or the key of another provider, see below).
   - `WOHNEN_ETHZ_LOGIN` / `WOHNEN_ETHZ_PASSWORD`: your wohnen.ethz.ch account.
   - `FLATFOX_LOGIN` / `FLATFOX_PASSWORD`: your Flatfox account.
   - `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`: the Gmail account that emails landlords (wohnen.ethz.ch). Use a Gmail [app password](https://support.google.com/mail/answer/185833?hl=en), not your normal one.
   - `CODE_INBOX_ADDRESS` / `CODE_INBOX_APP_PASSWORD`: the Gmail inbox that receives Flatfox's login codes (can be the same account).
   - `AUTO_HOUSE_PROFILE` / `AUTO_HOUSE_LLM`: optional defaults, so you can leave out `profile=` and `llm=`.

Variables already set in your shell take priority over `.env`.

**Coming from the original auto-house (`secret/<you>/`)?** Run `make migrate PROFILE=<you>`. It writes `conf/profile/<you>.yaml` from your two JSON files and copies your listing records to `data/<you>/`, so nobody gets contacted twice. It deletes and overwrites nothing. It does not copy passwords: it lists which `site_credentials.json` field goes into which `.env` variable, so you can move them by hand. Once `make status` looks right, delete `secret/<you>/`.

## LLM provider

| `llm=` | Default model | API key in `.env` |
|---|---|---|
| `deepseek` (default) | `deepseek-flash` | `DEEPSEEK_API_KEY` ([get one](https://platform.deepseek.com/)) |
| `openai` | `gpt-6-luna` | `OPENAI_API_KEY` |
| `claude` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |

Pick another model with `llm.model=...`, for example `llm=deepseek llm.model=deepseek-v4-pro`.

Check that your key works (one small, paid call):

```bash
uv run python main.py profile=<you> command=check-llm
```

Gemini is no longer supported: the model this project used (`gemini-2.0-flash`) was shut down in June 2026.

# Ready to go!

```bash
# See what the agent would send. Nothing is sent.
make dry-run PROFILE=<you> SITE=flatfox

# Review each draft, edit it if you like, and choose send / reject / later / quit.
make me-have-a-house PROFILE=<you> SITE=flatfox

# What happened to every listing so far.
make status PROFILE=<you>
```

Configuration uses [Hydra](https://hydra.cc/), so any setting can be changed on the command line:

```bash
uv run python main.py profile=<you> site=flatfox llm=claude mode=confirm min_fit=70
uv run python main.py profile=<you> site=flatfox --cfg job     # print the final config, run nothing
```

All settings and their defaults are in [conf/config.yaml](conf/config.yaml).

## Modes

| `mode=` | What it does |
|---|---|
| `dry-run` (default) | Checks fit and drafts messages. Nothing is sent. Drafts are saved, so a later `confirm` run reuses them without paying for them again. |
| `confirm` | Shows the fit score, red flags and review result for each draft and saves it as `data/<you>/<site>/_review.json` for editing. Sends only when you answer `s`. |
| `auto` | Sends drafts that passed review without asking, at most `max_sends` (default 5) per run. Use with care. |

Other settings: `min_fit` (default 60) is the lowest fit score to apply at.

## Tuning the agent

The instructions for each step are plain text in [prompts/](prompts/): `evaluate.md` (fit rubric), `draft.md` (how to write the message) and `review.md` (the checklist). Edit them to change the agent's behaviour; no code changes needed.

# Development

```bash
make test      # offline tests: no network, no API keys, no personal data needed
make format    # ruff format + autofix lint
make check     # what CI runs
```

Coding agents (Claude Code, Codex, ...) should read [AGENTS.md](AGENTS.md) first. In Claude Code, `/add-site <url>` walks through adding a new website.

Please open an issue if anything comes up, or make a pull request if you want to add a feature. See the [to-do list](TODO.md) for planned features.

# Tricks

- wgzimmer.ch runs through [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver). If it can't match your Chrome version, set `CHROME_VERSION_MAIN` to Chrome's major version (for example `CHROME_VERSION_MAIN=142`).
