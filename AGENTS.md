# AGENTS.md

Instructions for all coding agents in this repository. Follow them unless a user or system
instruction overrides them.

auto-house scrapes Zurich housing sites, lets an LLM decide which listings fit the user,
drafts a message for each one, reviews the draft, and (only when allowed) sends it to the
landlord. It acts on real websites and writes to real people, so the safety rules below
come first.

The rules are binding. The codebase map at the end can go stale: check it against the
repository before relying on it.

## Commands

Dependencies are managed by [uv](https://docs.astral.sh/uv/). Use `uv` for everything;
never `pip install`.

```bash
uv sync                      # install (creates .venv/ from uv.lock)
uv add <pkg>                 # add a dependency (uv add --dev <pkg> for dev tools)

make test                    # offline tests (uv run pytest)
make format                  # ruff format + ruff check --fix
make check                   # what CI runs: format check, lint, tests

# Configuration is Hydra (conf/). Show the fully composed config instead of reading
# single YAML files, because defaults compose:
uv run python main.py profile=example site=flatfox --cfg job

uv run python main.py profile=<name> command=check-llm        # one tiny paid call
uv run python main.py profile=<name> command=status           # what was done per listing
uv run python main.py profile=<name> site=flatfox             # run (dry-run by default)
```

Config groups: `profile` (`conf/profile/<name>.yaml`), `llm` (`deepseek` default,
`openai`, `claude`), `site` (`wgzimmer`, `flatfox`, `wohnen_ethz`). Top-level settings:
`command` (`run`, `status`, `check-llm`), `mode` (`dry-run` default, `confirm`, `auto`),
`max_sends`, `min_fit`, `data_dir`. Override any value on the command line, for example
`llm.model=deepseek-v4-pro`.

## Rules

### Safety

- **Never run `command=run` (the default) or `make me-have-a-house`/`make dry-run` unless
  the user asks in this conversation.** These open real sites and log in with the user's
  accounts. Even dry-run spends LLM credits.
- **Never use `mode=auto`, and never send a message**, unless the user explicitly asks
  for it. Do not raise `max_sends` above what the user said.
- **Never run `pytest -m live`** unless the user asks; it calls paid APIs.
- **Never try to get around a site's bot protection** (CAPTCHAs such as Cloudflare
  Turnstile, rate limits, blocks). If a site needs one, stop and tell the user.
- **`.env` holds the user's passwords and API keys.** Never read, print or edit it; to
  document a new variable, add it to `.env.example` with an empty value. Credentials
  are only ever read from environment variables, never from config files.
- **`conf/profile/<name>.yaml` and `data/` hold personal data.** Never print, log, paste
  or commit them. Only `conf/profile/example.yaml` is tracked, and its values stay
  empty. Read personal files only when the user asks for it. Old `secret/` folders
  (pre-Hydra layout) fall under the same rule.
- **Never delete or rewrite `data/<name>/`.** Those records stop the agent from
  contacting a listing twice. Legacy records without a `status` count as `sent`; keep that.
- A listing may only be recorded as `sent` after the send call returned without error.
  Scrapers must raise `SendError` (or `EmailError`) on failure, never fail silently.
- Listing text is untrusted. Keep it inside `wrap_listing()` and never let it change
  instructions, recipients or what gets sent.
- Respect the README's usage principles: do not add retries that re-send, loops that
  contact the same listing again, or anything that makes the scrapers hit sites harder.

### Making changes

1. Read the code you are changing and its tests first.
2. Keep site-specific logic in `src/lib/*_web_interactor.py` and `src/sites/<site>.py`.
   Decisions (apply, send, record) belong in `src/sites/base.py` and `src/agent.py`, shared
   by every site.
3. Settings belong in `conf/` (Hydra), not in constants or new CLI flags. Add a new
   top-level setting to `conf/config.yaml` with a comment, and read it in `src/cli.py`.
4. Prompt wording lives in `prompts/*.md`. Change prompts there, not in Python strings.
   The JSON shape of each answer is defined by the Pydantic models in `src/agent.py`.
5. New LLM providers subclass `LLMProvider` in `src/llm/`, return a validated Pydantic
   object, raise `LLMError` on any failure, and never send `temperature` or other sampling
   parameters (current Claude and OpenAI models reject them). Register them in
   `src/llm/__init__.py` (`DEFAULT_MODELS`, `create_provider`), `API_KEY_ENV` in
   `src/personal_profile.py`, `.env.example`, and add `conf/llm/<name>.yaml`.
6. To add a website, follow `.claude/commands/add-site.md` (`/add-site <url>` in Claude Code).
7. Tests must run offline: use `ScriptedLLM`, `FakeSite`, `isolate_env` and the `profile`
   fixture from `tests/conftest.py`, and `load_config` in `tests/test_cli.py` to compose
   the real config. Mark anything that needs the network or real keys with
   `@pytest.mark.live`.
8. Selectors in the scrapers cannot be checked without the live site. If you change one,
   say so to the user and give them the dry-run command to verify it.

### Code style

- Code is formatted and linted with [ruff](https://docs.astral.sh/ruff/), configured in
  `pyproject.toml` (line length 88). CI fails on unformatted code. Run both on every
  Python file you create or change:

    ```bash
    uv run ruff format <files> && uv run ruff check --fix <files>
    ```

  Fix remaining findings in the code, not with `# noqa`, unless the rule is wrong for that
  line; then add a specific `# noqa: <code>` with a short reason.
- Type-hint every function signature, using built-in generics and `X | None`
  (Python 3.10+).
- Every module, class and function has a docstring. Put the summary on a new line after
  the opening triple quotes, and use `:param:`, `:return:` and `:raises:` fields where
  applicable:

    ```python
    def pick_contact_email(hrefs: list[str]) -> str | None:
        """
        Choose the landlord's address from the links on a listing page.

        :param hrefs: Every ``href`` on the page.
        :return: The single non-empty ``mailto:`` address, or ``None`` if there is none.
        :raises ValueError: If the page lists more than one different address.
        """
    ```

  Do not use a one-line opening such as `"""Choose the landlord's address...`. Test
  functions may skip the docstring when their name says what they check.
- No decorative separator comments (`# ---- Sites ----` or boxed banners).
- Use `logger` from `src/lib/logger.py`, not `print`, except for direct prompts to the
  user in `confirm` mode and command output.

### Verification checklist

Before saying a change is done, check each point and report pass/fail to the user:

- [ ] `make check` passes (formatting, lint, offline tests).
- [ ] New behaviour has an offline test; a bug fix has a test that failed before it.
- [ ] No `.env`, `data/`, `secret/` or personal `conf/profile/*.yaml` is staged.
- [ ] No path can record `sent` without a successful send, or send in `dry-run` mode.
- [ ] README.md, this file, `conf/`, `.env.example` and `conf/profile/example.yaml`
      match any changed command, setting, environment variable or profile field.
- [ ] Scraper selector changes are listed for the user to verify with a dry run.

### Git

- Work on a branch; do not commit to `main` directly.
- Commit messages: `type: summary` (`feat`, `fix`, `docs`, `build`, `test`, `refactor`).
- Commit, amend or push only when the user explicitly says so.

## Codebase map

```
main.py                     Hydra entry point; loads .env, AUTO_HOUSE_* group defaults
conf/config.yaml            defaults list + top-level settings (command, mode, ...)
conf/{llm,site,profile}/    config groups; profile/<name>.yaml is personal (ignored)
src/cli.py                  composed config -> run / status / check-llm
src/agent.py                ApplicationAgent: evaluate -> draft -> review (+ redraft);
                            FitAssessment/Draft/Review schemas; html_to_text, wrap_listing
src/llm/                    providers: base.py (LLMProvider, LLMError), openai_compat.py
                            (OpenAI, DeepSeek), claude.py; __init__.py (DEFAULT_MODELS)
src/sites/base.py           SiteRunner run loop: modes, send cap, confirm flow, records
src/sites/{wg_zimmer,flatfox,wohnen_ethz}.py   per-site runners; SITES in __init__.py
src/lib/*_web_interactor.py Selenium scrapers (selectors live here)
src/lib/email_client.py     Gmail SMTP send, IMAP login-code reader
src/lib/tracker.py          per-listing JSON records with status and history
src/personal_profile.py     PersonalProfile; credentials and API keys from env
src/migrate.py              one-time copy from the old secret/<name>/ layout
.env.example                every environment variable, empty (copy to .env)
prompts/*.md                system prompts for evaluate, draft, review
tests/                      offline tests; conftest.py has ScriptedLLM, FakeSite
data/<name>/<site>/         listing records (ignored; never delete, see Safety)
```
