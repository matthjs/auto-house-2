RUN = uv run python main.py
# Optional: PROFILE=<you> SITE=<site>. Without PROFILE, AUTO_HOUSE_PROFILE in .env is used.
ARGS = $(if $(PROFILE),profile=$(PROFILE)) $(if $(SITE),site=$(SITE))

.PHONY: me-have-a-house dry-run status new-profile migrate test format lint check

# Live run: drafts each application and asks before sending it.
me-have-a-house:
	$(RUN) $(ARGS) mode=confirm

# Draft only; nothing is sent.
dry-run:
	$(RUN) $(ARGS) mode=dry-run

status:
	$(RUN) $(ARGS) command=status

# Create conf/profile/$(PROFILE).yaml from the example, and .env if it is missing.
new-profile:
	@test -n "$(PROFILE)" || (echo "Usage: make new-profile PROFILE=<name>" && exit 1)
	@test ! -e conf/profile/$(PROFILE).yaml || (echo "conf/profile/$(PROFILE).yaml already exists" && exit 1)
	cp conf/profile/example.yaml conf/profile/$(PROFILE).yaml
	@test -e .env || (cp .env.example .env && echo "Created .env; fill in your keys and logins.")

# One-time move from the old secret/<name>/ layout. Copies; deletes nothing.
migrate:
	@test -n "$(PROFILE)" || (echo "Usage: make migrate PROFILE=<name>" && exit 1)
	uv run python -m src.migrate $(PROFILE)

test:
	uv run pytest

format:
	uv run ruff format . && uv run ruff check --fix .

lint:
	uv run ruff format --check . && uv run ruff check .

check: lint test
