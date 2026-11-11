---
name: add-site
description: Add support for a new housing website to auto-house (scraper, site runner, config, tests). Use when the user wants the tool to search another site.
---

# Add a housing website

Add support for the site the user names. Follow the steps in order, and read AGENTS.md first.

## Step 1: Understand the site (no code yet)

Find out and report to the user:

- Does a search need a login? Does the login need an emailed code?
- How a landlord is contacted: a form on the site, or an email address on the listing.
- How results are listed: one page of links, pagination, or a "next" link per listing.
- A stable id in each listing URL (used to never contact a listing twice).
- Whether the site's terms or robots.txt forbid automated access, and whether it has a bot check (CAPTCHA). If access is forbidden, stop and tell the user. If only contacting is behind a bot check, the site is draft-only (`can_send = False`).
- Whether search and listing pages are public and server-rendered. If so, use plain HTTP like `src/lib/wg_zimmer_client.py`; only use Selenium when a login or JavaScript requires it.

Do not log in or submit anything on the live site. Reading public pages is fine.

Ask the user: "Should I go ahead and build this?" Stop if they say no.

## Step 2: Scraper

Create `src/lib/<site>_client.py` (HTTP) or `src/lib/<site>_web_interactor.py` (Selenium) following the existing ones:

- Keep page parsing in pure functions (like `parse_results` and `parse_listing`) so they can be tested offline on small synthetic HTML.
- `send_information` raises `SendError` (from `src/lib/errors.py`) when the site does not accept the message. Never return silently on failure.
- Prefer ids, names and stable attributes over generated CSS class names.

## Step 3: Runner

Create `src/sites/<site>.py` with a `SiteRunner` subclass (see `src/sites/wg_zimmer.py` for plain HTTP and draft-only, `src/sites/flatfox.py` for a public JSON API, `src/sites/email_alerts.py` for reading a portal's alert emails, `src/sites/wohnen_ethz.py` for email contact):

- Set `site` to the domain; it is also the data folder name.
- `required_fields()` lists the profile fields needed to search; `send_fields()` those needed to send.
- `listings()` yields `Listing` objects and logs and skips listings that fail to load.
- Register it in `SITES` in `src/sites/__init__.py` and add `conf/site/<key>.yaml` with `name: <key>` (the file name and key must match).

New logins or passwords go in `.env.example` (empty values) and `CREDENTIAL_ENV` in `src/search_profile.py`. Never put credentials in `conf/`.

## Step 4: Tests and checks

- Add offline tests for any pure helper you wrote (URL id parsing, contact extraction).
- Run `uv run ruff format . && uv run ruff check --fix .`, then `uv run ruff format --check . && uv run ruff check . && uv run pytest`; it must pass.
- Update the site list in README.md and the codebase map in AGENTS.md.

## Step 5: Hand over

Tell the user the exact dry-run command to try it themselves, for example `uv run python main.py search=<name> site=<key> command=search`. Do not run it yourself unless the user asks.
