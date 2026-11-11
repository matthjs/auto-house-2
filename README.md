# Welcome! 🚗🏠

Do you like to spend time looking for housing? No, neither do I!

Well, what about getting your own housing agent! An agent can be that for you: it crawls the housing sites, decides which offers actually fit you, and writes a personal message to each landlord.

> **Note:** this is a fork of [auto-house](https://github.com/MichalTesnar/auto-house) by [Michal Tesnar](https://github.com/MichalTesnar), who wrote the original scrapers and idea, with contributions from Ryan Slocum. This fork adds the agent loop (fit check, self-review), more LLM providers, a CLI and tests. If `auto-house` has helped you, consider starring the original repository as well.

# How it works

You talk to a coding agent (Claude Code or Codex) and it does the searching with you:

1. **Search.** It runs the tool, which finds new listings on the housing sites. This contacts nobody.
2. **Judge.** It scores each listing against your budget, place and deal breakers, flags anything that looks like a scam, and shows you a ranked table.
3. **Draft.** For the ones you pick, it writes a short message in the listing's language, using only facts about you (and your flatmates, if you search together), and checks it against a review list.
4. **You send.** You approve or tweak each message. On the websites you paste it in yourself (their contact forms have bot checks); for wohnen.ethz.ch it can email the landlord after your OK. Then it records the listing as sent.

Every listing gets a record in `data/<search>/<site>/` with its status (`found`, `skipped`, `shortlisted`, `drafted`, `needs_review`, `failed`, `rejected`, `sent`), the URL, the text, the fit and the message. A listing is never contacted twice, even if several people share a search.

There's also a **batch mode** without the chat: `uv run python main.py site=wgzimmer command=run` lets an API model (DeepSeek, Claude or OpenAI) judge every new listing in one cheap run and shortlist the good ones (messages are written in chat, only for the flats you pick; `batch_drafts=true` drafts them all). Run it as a daily job with [scripts/daily.sh](scripts/daily.sh) and everyone in the search gets one **email digest** with the new flats that fit, their rent and commute times (see [Daily job with an email digest](#daily-job-with-an-email-digest)).

**Dry run is on by default.** Nothing is sent, and no listing is marked as sent or rejected, unless the command gets `dry_run=false`. The agent only adds that after your OK for that one listing. (Searching and drafting still save their results in `data/`, so nothing is lost or paid for twice.)

# Usage

Please do not overuse this! The agent never responds to the same listing twice. Please do not modify it to send messages repeatedly.

Please use this moderately, and never try to get around a site's bot checks.

# Integrated websites

| Site | `site=` | Login needed | How landlords are contacted | Status (November 2026) |
|---|---|---|---|---|
| [WGZimmer.ch](https://www.wgzimmer.ch/home.html) | `wgzimmer` | No | You paste the message into the site's form | Works (plain HTTP) |
| [Flatfox.ch](https://flatfox.ch/c/en/) | `flatfox` | No | You use the site's form | Works (Flatfox's public API) |
| [WOKO](https://www.woko.ch/) (student rooms) | `woko` | No | You apply with WOKO's form | Works (one public page) |
| [Homegate](https://www.homegate.ch/), [ImmoScout24](https://www.immoscout24.ch/), [Comparis](https://www.comparis.ch/immobilien) | `email_alerts` | Gmail | You contact them on the portal | Reads the portals' own alert emails; untested until a real alert arrives |
| [Zimmer- und Wohnungsvermittlung Universität/ETH Zürich](https://www.wohnen.ethz.ch/) | `wohnen_ethz` | Yes | Email from your Gmail, after your OK | Site shows "Service not available" |

No browser is needed except for wohnen.ethz.ch. wgzimmer.ch and WOKO list single rooms in shared flats, which suit people searching alone; groups are better off on Flatfox and the big portals. WOKO only rents to students.

**Email alerts:** Homegate, ImmoScout24 and Comparis block scrapers, so the tool reads the saved-search alerts they email you instead. On each portal, save a search (place, budget, rooms) and turn on email alerts to the search contact's Gmail; `site=email_alerts` then reads the last 7 days of alerts. The listing text comes from the email, and you open the link to apply. If a portal changes its link format, adjust its `listing_pattern` in [conf/site/email_alerts.yaml](conf/site/email_alerts.yaml).

**Commute times:** list the places people in the search travel to (university, work) under `places` in the search file. Each Flatfox and WOKO listing then gets its public transport time to every place, from the free Swiss timetable API ([transport.opendata.ch](https://transport.opendata.ch/)), and the fit check weighs it against `max_commute_minutes`. Times are looked up once per listing. For groups, Flatfox also leaves out single rooms and flats with fewer than `min_rooms` rooms before anything is judged.

Not integrated: tutti.ch (blocks automated reading), JUWO (offers aren't on public pages), ronorp.net (listings load with JavaScript), Facebook groups.

# Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (and Google Chrome, only for wohnen.ethz.ch).
2. `uv sync`, then `cp .env.example .env`
3. Open [Claude Code](https://claude.com/claude-code) or [Codex](https://developers.openai.com/codex) in this folder and run **`/setup`** (Claude Code) or say **"set up auto-house"** (Codex). It checks the install, asks whether you search alone or together, your budget and what you're looking for, writes the config files, and explains the optional API key for batch mode.
4. Fill in `.env` with what it tells you. For wgzimmer.ch, Flatfox and WOKO in chat mode that's nothing at all; every variable is explained in [.env.example](.env.example).

Then say **"find me housing on wgzimmer"** (the `find-housing` skill).

**Without a coding agent:** copy `conf/person/example.yaml` to `conf/person/<you>.yaml` and `conf/search/example.yaml` to `conf/search/<you>.yaml`, fill them in by hand (set `members` and `contact` to `<you>`), add an API key to `.env`, and use batch mode.

## Where things live

| What | Where | In git? |
|---|---|---|
| Who each person is | `conf/person/<name>.yaml` | No |
| What a search is looking for, and who is in it | `conf/search/<name>.yaml` | No |
| Passwords and API keys | `.env` | No |
| What happened to each listing | `data/<search>/` | No |
| Settings and their defaults | [conf/config.yaml](conf/config.yaml) | Yes |

Only the `example.yaml` files are tracked. Searching together: one `conf/person/` file per person, and one search that lists them as `members` with one `contact`. The contact's accounts are used and landlords reply to them.

# Using the tool directly

The agent calls these commands, but you can too. Configuration is [Hydra](https://hydra.cc/), so any setting can be changed on the command line.

```bash
uv run python main.py search=<name> site=wgzimmer command=search    # new listings as JSON
uv run python main.py search=<name> command=status                  # every listing so far
uv run python main.py search=<name> site=wgzimmer command=show listing=<id>
uv run python main.py search=<name> site=wgzimmer command=mark listing=<id> decision=sent message_file=msg.md dry_run=false
uv run python main.py search=<name> site=wohnen_ethz command=send listing=<id> message_file=msg.md   # shows the email; add dry_run=false to send
uv run python main.py search=<name> site=wgzimmer command=run       # batch mode: judge and shortlist, sends nothing
uv run python main.py search=<name> site=wgzimmer --cfg job         # print the final config
```

A message file has an optional `Subject: ...` first line, then the message. Set `AUTO_HOUSE_SEARCH` in `.env` to leave out `search=`.

## Batch mode and API models

| `llm=` | Default model | API key in `.env` |
|---|---|---|
| `deepseek` | `deepseek-flash` | `DEEPSEEK_API_KEY` ([get one](https://platform.deepseek.com/)) |
| `claude` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-6-luna` | `OPENAI_API_KEY` |

Without `llm=`, the first provider whose key is set is used (in the order above). Pick another model with `llm.model=...`. Check a key with one small paid call: `uv run python main.py search=<name> command=check-llm`.

### Daily job with an email digest

[scripts/daily.sh](scripts/daily.sh) runs batch mode on Flatfox and the email alerts, then `command=digest`. The digest emails every member of the search (the `Email` in their person file, sent from the contact's Gmail with `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`) one message with the new flats that fit, best first: fit score and reasons, rent, rooms, start date, commute for each person and the link. Ask the agent to write the message for the ones you like. Each listing appears in one digest only, and no email goes out when nothing is new. The digest never emails landlords; you still send each message yourself.

```bash
uv run python main.py command=digest      # print the digest (digest.enabled is false by default)
scripts/daily.sh                          # the job: judges, then sends the digest
crontab -e                                # add: 0 7 * * * /path/to/auto-house-2/scripts/daily.sh >> /path/to/auto-house-2/out/daily.log 2>&1
```

On WSL, cron runs only while WSL is running, and its service may need `sudo service cron start`.

Batch mode uses the instructions in [prompts/](prompts/): `evaluate.md` (fit rubric), `draft.md` (how to write) and `review.md` (the checklist). The `find-housing` skill uses the same files, so editing them changes both.

# Development

```bash
uv run pytest                                      # offline tests: no network, keys or personal data
uv run ruff format . && uv run ruff check --fix .   # format and lint
uv run ruff format --check . && uv run ruff check . && uv run pytest   # what CI runs
```

Coding agents should read [AGENTS.md](AGENTS.md) first. The skills live in [.agents/skills/](.agents/skills/) (read by Codex; `.claude/skills` links there for Claude Code). The `add-site` skill walks through adding a new website.

Please open an issue if anything comes up, or make a pull request if you want to add a feature.
