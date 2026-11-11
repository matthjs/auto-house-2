# Welcome! 🚗🏠

Do you like to spend time looking for housing? No, neither do I!

Well, what about getting your own housing agent! An LLM can be that for you: it crawls the housing sites, decides which offers actually fit you, and writes a personal message to each landlord.

> **Credit:** this is a fork of [auto-house](https://github.com/MichalTesnar/auto-house) by [Michal Tesnar](https://github.com/MichalTesnar), who wrote the original scrapers and idea, with contributions from Ryan Slocum. This fork adds the agent loop (fit check, self-review), more LLM providers, a CLI and tests. If `auto-house` has helped you, consider starring the original repository!

# How it works

For every new listing on a site, the agent:

1. **Checks the fit.** It scores the listing from 0 to 100 against your budget, place, deal breakers and description, and flags anything that looks like a scam. Listings below the threshold are skipped and never looked at again.
2. **Drafts a message.** It first works out who will read it (a flatshare, a private landlord, an agency) and what they ask for. Then it writes a short message in the listing's language, using only facts from your description.
3. **Reviews the draft.** Fixed rules catch placeholders and bad length, and the LLM checks language, facts and tone. A failing draft is rewritten once with the feedback.
4. **Sends, if you allow it.** By default nothing is sent. See [Modes](#modes).

Every listing gets a record in `secret/<you>/data/<site>/` with its status (`skipped`, `drafted`, `needs_review`, `failed`, `rejected`, `sent`), the URL, the fit score, the draft and timestamps. A listing is never contacted twice, and it only counts as `sent` once the site or mail server accepted the message.

# Principles of usage

Please do not overuse this! The agent never responds to the same listing twice. Please do not modify it to send messages repeatedly.

The sites are not protected against bots. Please use this moderately so that they don't need to start protecting themselves.

# Integrated websites

| Site | `--site` | How landlords are contacted |
|---|---|---|
| [Zimmer- und Wohnungsvermittlung Universität/ETH Zürich](https://www.wohnen.ethz.ch/) | `wohnen-ethz` | Email from your Gmail |
| [WGZimmer.ch](https://www.wgzimmer.ch/home.html) | `wgzimmer` | Contact form on the site |
| [Flatfox.ch](https://flatfox.ch/c/en/) | `flatfox` | Contact form on the site |

# Setup

## Install

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Google Chrome.
2. `uv sync` (installs Python 3.10+ and all dependencies into `.venv/`).

## Your profile

1. `make new-profile PROFILE=<your-name>` copies `secret/example/` to `secret/<your-name>/`. Everything in `secret/` except the example is git-ignored.
2. Fill in `my_description.json`: who you are. The agent only uses facts from this file, so the more you put in, the better the messages.
3. Fill in `living_preferences.json`:
   - `budget_upper_bound`: maximum rent in CHF (required).
   - `place`: city for Flatfox and wohnen.ethz.ch, for example `Zürich`.
   - `place_wg_zimmer`: the region value from wgzimmer.ch's search form, for example `zurich-stadt`.
   - `move_in_date`, `nice_to_haves`, `deal_breakers`: optional, used by the fit check.
4. Fill in `site_credentials.json` for the sites you use:
   - `wohnen_ethz_login` / `wohnen_ethz_password`: your wohnen.ethz.ch account.
   - `flatfox_login` / `flatfox_password`: your Flatfox account.
   - `login` / `password`: the Gmail account that sends emails (wohnen.ethz.ch). Use a Gmail [app password](https://support.google.com/mail/answer/185833?hl=en), not your normal one.
   - `login2` / `password2`: the Gmail inbox that receives Flatfox's login codes (can be the same account).
   - API key of your LLM provider (see below).

## LLM provider

| `--provider` | Default model | Key (environment variable, or field in `site_credentials.json`) |
|---|---|---|
| `deepseek` (default) | `deepseek-flash` | `DEEPSEEK_API_KEY` / `DeepSeek_API_KEY` ([get one](https://platform.deepseek.com/)) |
| `openai` | `gpt-6-luna` | `OPENAI_API_KEY` / `OpenAI_API_KEY` |
| `claude` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` / `Anthropic_API_KEY` |

Pick another model with `--model`, for example `--provider deepseek --model deepseek-v4-pro`. Set `AUTO_HOUSE_PROVIDER` and `AUTO_HOUSE_PROFILE` to skip typing them every time.

Check that your key works (one small, paid call):

```bash
uv run python main.py check-llm --profile <your-name>
```

Gemini is no longer supported: the model this project used (`gemini-2.0-flash`) was shut down in June 2026.

# Ready to go!

```bash
# See what the agent would send. Nothing is sent.
make dry-run PROFILE=<your-name> SITE=wgzimmer

# Review each draft, edit it if you like, and choose send / reject / later / quit.
make me-have-a-house PROFILE=<your-name> SITE=wgzimmer

# What happened to every listing so far.
make status PROFILE=<your-name>
```

Or call the CLI directly: `uv run python main.py run --help`.

## Modes

| `--mode` | What it does |
|---|---|
| `dry-run` (default) | Checks fit and drafts messages. Nothing is sent. Drafts are saved, so a later `confirm` run reuses them without paying for them again. |
| `confirm` | Shows the fit score, red flags and review result for each draft and opens it as `secret/<you>/data/<site>/_review.json` for editing. Sends only when you answer `s`. |
| `auto` | Sends drafts that passed review without asking, at most `--max-sends` (default 5) per run. Use with care. |

Other options: `--min-fit` (default 60) is the lowest fit score to apply at.

## Tuning the agent

The instructions for each step are plain text in [prompts/](prompts/): `evaluate.md` (fit rubric), `draft.md` (how to write the message) and `review.md` (the checklist). Edit them to change the agent's behaviour; no code changes needed.

# Development

```bash
make test      # offline tests: no network, no API keys, no secrets needed
make format    # ruff format + autofix lint
make check     # what CI runs
```

Coding agents (Claude Code, Codex, ...) should read [AGENTS.md](AGENTS.md) first. In Claude Code, `/add-site <url>` walks through adding a new website.

Please open an issue if anything comes up, or make a pull request if you want to add a feature. See the [to-do list](TODO.md) for planned features.

# Tricks

- wgzimmer.ch blocks regular Selenium, so it runs through [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver). If it can't match your Chrome version, set `CHROME_VERSION_MAIN` to Chrome's major version (for example `CHROME_VERSION_MAIN=142`).
