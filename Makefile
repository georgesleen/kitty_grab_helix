# One command surface: the same commands CI and the pre-push hook run.
.PHONY: check fmt lint test

check: lint test

test:
	pytest -q

lint:
	ruff check .
	nixfmt --check ./*.nix

fmt:
	ruff format .
	nixfmt ./*.nix
