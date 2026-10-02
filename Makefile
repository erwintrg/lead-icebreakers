PYTHON ?= python3

.PHONY: demo test install install-drive install-dev clean

demo:  ## offline demo with the mock backend, no key needed
	$(PYTHON) demo.py

test:  ## run the test suite (pip install -r requirements-dev.txt first)
	$(PYTHON) -m pytest

install:  ## real mode: Anthropic SDK and .env loading
	$(PYTHON) -m pip install -r requirements.txt

install-drive:  ## optional Google Drive hand-off
	$(PYTHON) -m pip install -r requirements-drive.txt

install-dev:  ## pytest
	$(PYTHON) -m pip install -r requirements-dev.txt

clean:
	rm -rf out .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
