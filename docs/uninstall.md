# Uninstalling HelloAGI

## PyPI / user install

```bash
helloagi uninstall --yes
```

If the `helloagi` command is not on PATH yet:

```bash
python -m pip uninstall helloagi
```

## Remove generated runtime files

```bash
rm -f helloagi.json helloagi.onboard.json
rm -rf memory/
```

## Windows PowerShell cleanup

```powershell
python -m pip uninstall helloagi
Remove-Item helloagi.json, helloagi.onboard.json -ErrorAction SilentlyContinue
Remove-Item memory -Recurse -Force -ErrorAction SilentlyContinue
```
