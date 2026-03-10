# Install & Run

## Option A: Local package target (no root needed)
```bash
python3 -m pip install . --target ./_local_install
PYTHONPATH=./_local_install python3 -m agi_runtime.cli init
PYTHONPATH=./_local_install python3 -m agi_runtime.cli run --goal "Build useful intelligence"
```

## Option B: Docker
```bash
docker build -t helloagi:latest .
docker run --rm -p 8787:8787 helloagi:latest
```

## Verify
```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/chat -H 'content-type: application/json' -d '{"message":"help me build an agent"}'
```
