RUN = uv run python main.py
# Optional: SEARCH=<name> SITE=<site>. Without SEARCH, AUTO_HOUSE_SEARCH in .env is used.
ARGS = $(if $(SEARCH),search=$(SEARCH)) $(if $(SITE),site=$(SITE))

.PHONY: me-have-a-house search status new-search migrate test format lint check

# Batch mode: the API model judges and drafts every new listing. Sends nothing
# (dry_run is on by default); review the drafts with the find-housing skill.
me-have-a-house:
	$(RUN) $(ARGS) command=run

# List new listings as JSON; contacts nobody.
search:
	$(RUN) $(ARGS) command=search

status:
	$(RUN) $(ARGS) command=status

# Start a one-person search from the examples (for groups, use the setup skill).
new-search:
	@test -n "$(SEARCH)" || (echo "Usage: make new-search SEARCH=<name>" && exit 1)
	@test ! -e conf/search/$(SEARCH).yaml || (echo "conf/search/$(SEARCH).yaml already exists" && exit 1)
	cp conf/person/example.yaml conf/person/$(SEARCH).yaml
	sed 's/example/$(SEARCH)/g' conf/search/example.yaml > conf/search/$(SEARCH).yaml
	@test -e .env || (cp .env.example .env && echo "Created .env; fill in what your sites need.")

# One-time move from the old secret/<name>/ layout. Copies; deletes nothing.
migrate:
	@test -n "$(SEARCH)" || (echo "Usage: make migrate SEARCH=<name>" && exit 1)
	uv run python -m src.migrate $(SEARCH)

test:
	uv run pytest

format:
	uv run ruff format . && uv run ruff check --fix .

lint:
	uv run ruff format --check . && uv run ruff check .

check: lint test
