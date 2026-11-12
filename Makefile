.PHONY: sources ingest inventory test
sources:
	python3 ingest/download.py list
ingest:
	python3 ingest/download.py fetch --group core
inventory:
	python3 ingest/download.py inventory --check-core
test:
	python3 -m unittest discover -s tests -v
