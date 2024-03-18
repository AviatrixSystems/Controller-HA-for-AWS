bin/aviatrix_ha.zip:
	@rm -rf $@ .venv-lambda
	poetry bundle venv --only=main .venv-lambda
	(cd .venv-lambda/lib/python*/site-packages/ && zip -r ../../../../$@ . -x '*.pyc' -x '__pycache__' -x '*.so')

.PHONY: test
test:
	poetry run pytest

.PHONY: pylint
pylint:
	poetry run pylint aviatrix_ha -E

.PHONY: black
black:
	poetry run black aviatrix_ha
