# Platform Support

## Runtime

- Windows: supported
- macOS: supported
- Linux: supported

## Native service backend

- Windows: Scheduled Task
- macOS: `launchd`
- Linux: `systemd --user`

## Install paths

- Hosted installer scripts
- PyPI / `python -m pip install`
- Source install from a clone
- Docker for HTTP API workflows

## Recommended patterns

- Use a virtual environment for development and local CLI use.
- Use `helloagi service install` for always-on personal-assistant setups.
- Keep config, `.env`, and `memory/` in the working directory you want the service to own.
