# Welcome! 🚗🏠

Do you like to spend time looking for housing? No, neither do I!

Well, what about getting your own housing agent! An agent can be that for you: it crawls the housing sites, decides which offers actually fit you, and writes a personal message to each landlord.

> **Note:** this is a fork of [auto-house](https://github.com/MichalTesnar/auto-house) by [Michal Tesnar](https://github.com/MichalTesnar), who wrote the original scrapers and idea, with contributions from Ryan Slocum. This fork adds the agent loop (fit check, self-review), more LLM providers, a CLI and tests. If `auto-house` has helped you, consider starring the original repository as well.

## How it works

There are three ways to use it, and they work together.

### Daily email (automatic)

1. **Every morning** a cheap API model (DeepSeek, Claude or OpenAI) checks the new listings on the housing sites against your budget, rooms, commute and deal breakers.
2. **You get one email** (everyone in the search does) with the flats that fit, best first: score, pros and cons, rent, start date, commute per person and the link.
3. **For a flat you like**, ask your coding agent to write the message (see below).

### Chat with your coding agent (no API key needed)

Open [Claude Code](https://claude.com/claude-code) or [Codex](https://developers.openai.com/codex) in this folder and say **"find me housing"**, or "write a message for the Hofwiesenstrasse flat":

1. **Search.** It runs the tool, which finds new listings on the housing sites. This contacts nobody.
2. **Judge.** It scores each listing against your budget, place, commute and deal breakers, flags anything that looks like a scam, and shows you a ranked table.
3. **Draft.** For the ones you pick, it writes a short message in the listing's language, using only facts about you (and your flatmates, if you search together), and checks it against a review list.
4. **You send.** You approve or tweak each message and paste it into the site yourself (for wohnen.ethz.ch it can email the landlord after your OK). Then it records the listing as sent.

### Batch mode (no email, no chat)

Let the API model judge all new listings on a site in one run, whenever you like:

```bash
uv run python main.py site=flatfox command=run                    # judge and shortlist
uv run python main.py site=flatfox command=run batch_drafts=true  # also draft a message for each good flat
uv run python main.py command=status                              # see the results
```

This is what the daily job runs before sending the email. Your coding agent can pick up the shortlist in chat.

In every case, nothing is ever sent to a landlord without you, and a listing is never contacted twice.

## Features

- **Daily email digest:** one email per day to everyone in the search, only when there is something new, and each flat only once.
- **Searching together:** several people in one search, with one contact person landlords reply to. Single rooms and flats that are too small are left out.
- **Commute times:** public transport time from each flat to the places each person goes (university, office), counted in the score.
- **Messages that check themselves:** drafts are reviewed for invented facts, placeholders and length, and rewritten once if needed.
- **Choice of model:** DeepSeek, Claude or OpenAI, picked from whichever API key you set.
- **Scam and prompt-injection checks:** suspicious listings and instructions hidden in listing text are flagged, never followed.
- **Dry run by default:** no command sends anything or marks a listing without `dry_run=false`, which the agent only adds after your OK for that one listing.
- **A record of every listing** in `data/<search>/` (found, skipped, shortlisted, drafted, sent, ...), so nothing is judged or paid for twice.
- **New sites** can be added with the `add-site` skill.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

    ```bash
    uv sync
    cp .env.example .env
    ```

2. In this folder, open [Claude Code](https://claude.com/claude-code) and run **`/setup`** (in [Codex](https://developers.openai.com/codex): say "set up auto-house"). It asks who is searching, your budget, rooms, move-in date and the places you commute to, and writes your config files.

That's all you need for chat mode: say **"find me housing"**. For the daily email:

3. Fill in `.env` (every variable is explained in [.env.example](.env.example)):
    - an API key, for example `DEEPSEEK_API_KEY` (cheapest; [get one](https://platform.deepseek.com/));
    - `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` (a Gmail [app password](https://support.google.com/mail/answer/185833)), to send the email and read portal alerts;
    - `AUTO_HOUSE_SEARCH=<your search>`, so commands don't need `search=`.
4. Test it once. This judges the new listings and sends the email:

    ```bash
    uv run python main.py command=check-llm   # one tiny paid call
    scripts/daily.sh                          # one real run
    ```

5. Run it every morning at 07:00 (`crontab -e`):

    ```
    0 7 * * * /path/to/auto-house-2/scripts/daily.sh >> /path/to/auto-house-2/out/daily.log 2>&1
    ```

    On WSL, cron only runs while WSL is running; start it with `sudo service cron start` if needed.

**Without a coding agent:** copy the `example.yaml` files in `conf/person/` and `conf/search/`, fill them in, and do steps 3 to 5.

## Sites

| Site | `site=` | Login | How you apply | Status (November 2026) |
|---|---|---|---|---|
| [Flatfox.ch](https://flatfox.ch/c/en/) | `flatfox` | No | On the site | Works (public API) |
| [Homegate](https://www.homegate.ch/), [ImmoScout24](https://www.immoscout24.ch/), [Comparis](https://www.comparis.ch/immobilien) | `email_alerts` | Gmail | On the portal | Reads their alert emails; not yet tested on a real alert |
| [WGZimmer.ch](https://www.wgzimmer.ch/home.html) | `wgzimmer` | No | On the site | Works |
| [WOKO](https://www.woko.ch/) (students only) | `woko` | No | WOKO's form | Works |
| [wohnen.ethz.ch](https://www.wohnen.ethz.ch/) | `wohnen_ethz` | Yes | Email, after your OK | Site shows "Service not available" |

The daily job searches Flatfox and the portal alerts; pass other sites as arguments (`scripts/daily.sh flatfox woko`). wgzimmer.ch and WOKO list single rooms, which suit people searching alone. Only wohnen.ethz.ch needs Google Chrome.

**Portal alerts:** Homegate, ImmoScout24 and Comparis block scrapers, so on each portal save a search (place, budget, rooms) with email alerts to your Gmail. The tool reads those emails (read-only, last 7 days).

Not integrated: tutti.ch (blocks automated reading), JUWO (no public offers), ronorp.net (JavaScript only), Facebook groups.

## Where things live

| What | Where | In git? |
|---|---|---|
| Who each person is | `conf/person/<name>.yaml` | No |
| What a search looks for, who is in it, commute places | `conf/search/<name>.yaml` | No |
| Passwords and API keys | `.env` | No |
| What happened to each listing | `data/<search>/` | No |
| Settings and defaults | [conf/config.yaml](conf/config.yaml) | Yes |
| Fit rubric, writing rules, review checklist | [prompts/](prompts/) | Yes |

Only the `example.yaml` files are tracked.

## Commands

Your coding agent runs these, but you can too. Settings are [Hydra](https://hydra.cc/) config, so any of them can be changed on the command line.

```bash
uv run python main.py site=flatfox command=run            # judge new listings (API)
uv run python main.py command=digest                      # show the email; digest.enabled=true sends it
uv run python main.py command=status                      # every listing so far
uv run python main.py site=flatfox command=search         # new listings as JSON (no API)
uv run python main.py site=flatfox command=show listing=<id>
uv run python main.py site=flatfox command=mark listing=<id> decision=sent dry_run=false
uv run python main.py site=wohnen_ethz command=send listing=<id> message_file=msg.md   # add dry_run=false to send
uv run python main.py site=flatfox --cfg job              # print the final config
```

| `llm=` | Default model | Key in `.env` |
|---|---|---|
| `deepseek` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| `claude` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-6-luna` | `OPENAI_API_KEY` |

The first provider with a key is used; choose another with `llm=` and `llm.model=`. Other settings: `min_fit` (lowest score in the email, default 60), `batch_drafts=true` (also write a message for every flat that fits), `max_commute_minutes` and `places` in your search file.

## Fair use

Please don't overuse this, don't change it to message the same listing again, and never try to get around a site's bot checks.

## Development

```bash
uv run ruff format --check . && uv run ruff check . && uv run pytest   # what CI runs
```

Tests run offline, with no network, keys or personal data. Coding agents should read [AGENTS.md](AGENTS.md) first. The skills live in [.agents/skills/](.agents/skills/) (`.claude/skills` links there).

Please open an issue if anything comes up, or a pull request if you want to add a feature.
