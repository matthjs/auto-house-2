PROFILE ?= $(AUTO_HOUSE_PROFILE)
SITE ?= wgzimmer
RUN = uv run python main.py

.PHONY: me-have-a-house dry-run status new-profile test format lint check

# Live run: drafts each application and asks before sending it.
me-have-a-house:
	$(RUN) run --profile $(PROFILE) --site $(SITE) --mode confirm

# Draft only; nothing is sent.
dry-run:
	$(RUN) run --profile $(PROFILE) --site $(SITE) --mode dry-run

status:
	$(RUN) status --profile $(PROFILE)

# Create secret/$(PROFILE)/ from the example templates.
new-profile:
	@test -n "$(PROFILE)" || (echo "Usage: make new-profile PROFILE=<name>" && exit 1)
	@test ! -e secret/$(PROFILE) || (echo "secret/$(PROFILE) already exists" && exit 1)
	cp -r secret/example secret/$(PROFILE)

test:
	uv run pytest

format:
	uv run ruff format . && uv run ruff check --fix .

lint:
	uv run ruff format --check . && uv run ruff check .

check: lint test
