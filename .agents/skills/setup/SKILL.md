---
name: setup
description: Set up auto-house - check the install, create a housing search for one person or a group (who, budget, place, preferences), and set up the API key for batch mode if wanted. Also for changes later, such as a new budget or adding someone. Use when the user starts using auto-house or wants to change their search.
---

# Setup

You get the user from zero to a working search, and you write every config file
yourself so nobody edits YAML. Read AGENTS.md first. Never read or write `.env`.

## Step 0: Choose the path

Look at `conf/search/` (ignore `example.yaml`) and check whether a `secret/` folder exists. Then greet the user in one short message and offer what applies:

- **New search** (no searches yet): "I'll ask who's searching, your budget and what you're looking for. Takes about five minutes."
- **Import**: "Paste a CV, LinkedIn summary or a short bio for each person and I'll fill in what I can." If `secret/<name>/` exists (the original auto-house), offer `uv run python -m src.migrate <name>` instead.
- **Change an existing search**: budget, place, preferences, adding or removing a person, changing the contact. Read the files, change only what was asked, show the change, and skip to Step 6.

## Step 1: Install check

Run `uv sync`. Check whether `.env` exists with `test -e .env && echo yes` (never open it). If it doesn't, ask the user to run `cp .env.example .env` themselves; your settings block writing to `.env`. Google Chrome is only needed for wohnen.ethz.ch; mention it in Step 5 if they pick that site.

## Step 2: Who is searching

Ask: "Are you searching alone or together? What are everyone's first names? Who should landlords contact?"

- Use lowercase file names (`anna`, `ben`). The search name is the names joined with `_` (`anna_ben`), or the single name.
- The **contact** is the person landlords reply to; their site logins and Gmail are used.
- For a group, recommend that one person (usually the contact) runs the tool on their machine; the others only give their details. Two machines would each keep their own `data/` records and could contact the same listing twice.

## Step 3: Each person

For each person ask in one message (everything optional except the name), or extract it from what they pasted and ask only for what's missing:

- Name, age, nationality, occupation (study or job, where)
- Languages spoken
- Phone and email (needed for the contact person)
- What they like, lifestyle (tidy, cooks, sports, quiet, ...), LinkedIn or blog

Write `conf/person/<name>.yaml` in the shape of `conf/person/example.yaml`. Use only what the person said or pasted; leave the rest empty. Show a short summary and ask if it's right.

## Step 4: What the search is looking for

Ask:

- **Budget:** maximum total rent in CHF for everyone together (required).
- **Place:** city for wohnen.ethz.ch (e.g. `Zürich`) and the wgzimmer.ch region (e.g. `zuerich`, `kanton-zuerich`). Flatfox searches the city of Zurich by default; for another area, change `bbox` in `conf/site/flatfox.yaml`.
- **Rooms** (groups): minimum number of rooms; default one bedroom each.
- Move-in date, nice-to-haves, deal breakers.
- **Places and commute:** where does each person go most days (university building, office)? Look up the address if they only name the place, and confirm it with them. Ask the longest trip they accept (`max_commute_minutes`). These go under `places` (name, address as `Street 1, 8000 Town`, `who`); Flatfox and WOKO listings then get public transport times to each.
- **Sites:** `wgzimmer` (single rooms in shared flats; suits someone alone), `woko` (student rooms; students only), `flatfox` (flats and rooms; good for groups), `email_alerts` (Homegate, ImmoScout24 and Comparis through their alert emails; they set up the alerts on each portal, sent to the contact's Gmail), `wohnen_ethz` (login; ETH/UZH housing office, contact by email). None of these needs a site login except wohnen.ethz.ch.

Write `conf/search/<search>.yaml` in the shape of `conf/search/example.yaml`, with `members` and `contact` set.

## Step 5: Accounts and API key

Explain the two ways of working, then ask which they want:

- **Chat mode (default):** you (Claude Code or Codex) judge listings and write messages together with the user. **No API key needed.**
- **Batch mode (optional):** `uv run python main.py site=<site> command=run` lets an API model judge and draft every new listing in one go, for example as a daily job, without a chat. Needs one API key:
  - DeepSeek (cheapest; recommended): `DEEPSEEK_API_KEY`, from https://platform.deepseek.com/
  - Claude: `ANTHROPIC_API_KEY`, from https://console.anthropic.com/
  - OpenAI: `OPENAI_API_KEY`, from https://platform.openai.com/
  The tool uses whichever key is set; `AUTO_HOUSE_LLM` picks one if several are.

Then tell the user exactly which lines to fill in `.env` themselves, based on their sites and choice:

- wgzimmer.ch, Flatfox, WOKO in chat mode: nothing.
- Email alerts: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (a Gmail [app password](https://support.google.com/mail/answer/185833)). Also explain how to set up the alerts on each portal: save a search with their place, budget and rooms, and turn on email alerts to that Gmail address.
- wohnen.ethz.ch: `WOHNEN_ETHZ_LOGIN`, `WOHNEN_ETHZ_PASSWORD`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and Google Chrome installed.
- Batch mode: the one API key from above.
- Recommended: `AUTO_HOUSE_SEARCH=<search>`, so commands don't need `search=`.

Wait until they say they've filled it in.

## Step 6: Check

- Run `uv run python main.py search=<search> command=status`. Every site should say "no listings yet" (or show migrated records).
- If they set up batch mode, offer one small paid test: `uv run python main.py search=<search> command=check-llm`.
- Run `git status` and confirm none of the new person, search or data files is tracked (they are git-ignored).

Finish with a two-line summary of the search (who, budget, sites) and offer to start the find-housing skill.
