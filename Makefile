PYTHON ?= .venv/bin/python
ACTIONLINT ?= $(shell go env GOPATH)/bin/actionlint
SHA ?=
OUT ?= /tmp/hiroba-scaffold

.PHONY: setup lint unit test-negative test-scaffold render-scaffold verify-evidence
setup:
	python3 -m venv .venv
	.venv/bin/pip install --disable-pip-version-check -r requirements-dev.txt

lint:
	$(ACTIONLINT) .github/workflows/*.yml
	$(PYTHON) -m yamllint -c .yamllint.yaml .github/workflows scaffold/.github/workflows
	find scripts scaffold/packages -type f -name '*.sh' -print0 | xargs -0 shellcheck
	$(PYTHON) scripts/check-workflow-pins.py --root .
	$(PYTHON) scripts/check-workflow-pins.py --root scaffold
	$(PYTHON) -c 'import json,pathlib,jsonschema; [jsonschema.validators.validator_for(s).check_schema(s) for p in pathlib.Path("schemas").glob("*.json") for s in [json.loads(p.read_text())]]; print("JSON Schemas valid")'

unit:
	$(PYTHON) -m unittest discover -s tests/unit -p 'test_*.py'

test-negative:
	$(PYTHON) -m unittest discover -s tests/integration -p 'test_*.py'

test-scaffold:
	$(PYTHON) scripts/validate-repository.py --root scaffold --registry tests/fixtures/app-registry.yaml
	$(PYTHON) scripts/build-indexes.py --root scaffold --check
	$(PYTHON) scripts/sync-release-please-config.py --root scaffold --check
	$(PYTHON) scripts/render-observability.py --root scaffold --check

render-scaffold:
	@test -n "$(SHA)" || (echo 'SHA is required' >&2; exit 2)
	scripts/render-scaffold.sh --source scaffold --out "$(OUT)" --sha "$(SHA)"
	$(PYTHON) scripts/check-workflow-pins.py --root "$(OUT)" --require-rendered

verify-evidence:
	$(PYTHON) -m unittest tests.unit.test_trusted_evidence tests.unit.test_sign_and_verify tests.unit.test_package_publish tests.unit.test_release_chart tests.unit.test_finalize_release
