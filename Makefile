SRC_FILES = $(shell find aviatrix_ha -name "*.py")

bin/aviatrix_ha.zip: $(SRC_FILES) pyproject.toml poetry.lock
	@rm -rf $@ .venv-lambda
	poetry bundle venv --only=main .venv-lambda
	(cd .venv-lambda/lib/python*/site-packages/ && zip -r ../../../../$@ . -x '*.pyc' -x '__pycache__' -x '*.so')

bin/aviatrix_ha_dev.zip: $(SRC_FILES) pyproject.toml poetry.lock
	@rm -rf $@ .venv-lambda
	poetry bundle venv --only=main .venv-lambda
	(cd .venv-lambda/lib/python*/site-packages/ && touch dev_flag && zip -r ../../../../$@ . -x '*.pyc' -x '__pycache__' -x '*.so')

cft/aviatrix-aws-existing-controller-ha-dev.json: cft/aviatrix-aws-existing-controller-ha.json
	sed 's/aviatrix_ha.zip/aviatrix_ha_dev.zip/' $< > $@

.PHONY: push
push: bin/aviatrix_ha.zip
	poetry run python3 scripts/push_to_s3.py --lambda_zip_file=bin/aviatrix_ha.zip --cft_file=cft/aviatrix-aws-existing-controller-ha.json

.PHONY: push_dev
push_dev: bin/aviatrix_ha_dev.zip cft/aviatrix-aws-existing-controller-ha-dev.json
	poetry run python3 scripts/push_to_s3.py --dev --lambda_zip_file=bin/aviatrix_ha_dev.zip --cft_file=cft/aviatrix-aws-existing-controller-ha-dev.json

.PHONY: clean
clean:
	rm -rf bin/*.zip
	rm -f cft/aviatrix-aws-existing-controller-ha-dev.json

.PHONY: test
test:
	poetry run pytest

.PHONY: pylint
pylint:
	poetry run pylint aviatrix_ha -E

.PHONY: black
black:
	poetry run black aviatrix_ha
