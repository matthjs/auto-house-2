---
description: Add support for a new housing website
argument-hint: <site URL>
---

# /add-site: add a housing website

Add support for the site at `$ARGUMENTS`. Follow the steps in order, and read AGENTS.md first.

## Step 1: Understand the site (no code yet)

Find out and report to the user:

- Does a search need a login? Does the login need an emailed code?
- How a landlord is contacted: a form on the site, or an email address on the listing.
- How results are listed: one page of links, pagination, or a "next" link per listing.
- A stable id in each listing URL (used to never contact a listing twice).
- Whether the site's terms forbid automated access. If they do, stop and tell the user.

Do not log in or submit anything on the live site. Reading public pages is fine.

Ask the user: "Should I go ahead and build this?" Stop if they say no.

## Step 2: Scraper

Create `src/lib/<site>_web_interactor.py` following the existing interactors:

- Methods `load`, `enter`, `search`, `gather_results`, `visit_and_gather`, `close`, and `send_information` if contact goes through a form.
- `send_information` raises `SendError` (from `src/lib/errors.py`) when the site does not accept the message. Never return silently on failure.
- Prefer ids, names and stable attributes over generated CSS class names.

## Step 3: Runner

Create `src/sites/<site>.py` with a `SiteRunner` subclass (see `src/sites/flatfox.py` for URL lists, `src/sites/wg_zimmer.py` for "next" links, `src/sites/wohnen_ethz.py` for email contact):

- Set `site` to the domain; it is also the data folder name.
- `required_fields()` lists the profile fields needed, with contact/sending fields only when `self.mode != "dry-run"`.
- `listings()` yields `Listing` objects and logs and skips listings that fail to load.
- Register it in `SITES` in `src/sites/__init__.py` and add `conf/site/<key>.yaml` with `name: <key>` (the file name and key must match).

New logins or passwords go in `.env.example` (empty values) and `CREDENTIAL_ENV` in `src/personal_profile.py`. Never put credentials in `conf/`.

## Step 4: Tests and checks

- Add offline tests for any pure helper you wrote (URL id parsing, contact extraction).
- Run `make format` and `make check`; both must pass.
- Update the site list in README.md and the codebase map in AGENTS.md.

## Step 5: Hand over

Tell the user the exact dry-run command to try it themselves, for example `make dry-run PROFILE=<name> SITE=<key>`. Do not run it yourself unless the user asks.
