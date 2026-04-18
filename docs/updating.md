# Updating HelloAGI

## Hosted installer

Re-run the installer you used originally.

You can also update from any existing install with:

```bash
helloagi update
```

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.ps1 | iex
```

## PyPI install

```bash
python -m pip install --user --upgrade "helloagi[rich,telegram]"
```

## Git install

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash -s -- --source git --ref main
```

## Verify after update

```bash
helloagi tools
helloagi health
helloagi extensions doctor
helloagi service status
python -m agi_runtime.cli doctor
python -m agi_runtime.cli onboard-status
```
