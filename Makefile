.PHONY: test run serve init doctor

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

init:
	PYTHONPATH=src python3 -m agi_runtime.cli init

doctor:
	PYTHONPATH=src python3 -m agi_runtime.cli doctor

run:
	PYTHONPATH=src python3 -m agi_runtime.cli run --goal "Build useful intelligence"

serve:
	PYTHONPATH=src python3 -m agi_runtime.cli serve --host 127.0.0.1 --port 8787
