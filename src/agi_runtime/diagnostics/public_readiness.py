from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
import re
import subprocess
from typing import Iterable


@dataclass
class PublicReadinessCheck:
    name: str
    ok: bool
    detail: str
    action: str = ""


_RUNTIME_PATTERNS = [
    r"(^|/)\.env(\..*)?$",
    r"(^|/)helloagi\.json$",
    r"(^|/)helloagi\.onboard\.json$",
    r"(^|/)memory/.*\.(json|jsonl|db|sqlite|sqlite3)$",
    r"(^|/)memory/.*openai_codex_oauth.*",
    r"(^|/)memory/.*auth_profiles.*",
    r"(^|/)[^/]*(secret|secrets|token|credential|credentials|auth)[^/]*\.(json|ya?ml|toml|txt|env)$",
    r"(^|/).*\.log$",
]

_BENIGN_TRACKED_RUNTIME = {
    ".env.example",
    "tests/test_provider_credentials.py",
}

_REQUIRED_DOCS = [
    "README.md",
    "docs/install.md",
    "docs/cli-reference.md",
    "docs/channels.md",
    "docs/deployment.md",
    "docs/environment.md",
    "docs/security.md",
    "docs/privacy.md",
    "docs/troubleshooting.md",
    "docs/production-checklist.md",
]

_ORGANISM_ARCHITECTURE_TERMS = {
    "brain": ["brain", "cortex", "context unrolling", "verifier"],
    "nervous": ["nervous", "event", "trace"],
    "senses": ["senses", "channels", "cli", "api"],
    "effectors": ["effectors", "muscles", "tools", "action"],
    "immune": ["immune", "srg", "approval", "governance"],
    "memory": ["memory", "hippocampus", "skill"],
    "metabolism": ["metabolism", "budget", "rate", "cost"],
    "homeostasis": ["homeostasis", "health", "degraded", "recovery"],
    "growth": ["growth", "crystallization", "benchmark", "scorecard"],
}

_PRIVATE_TEXT_PATTERNS = [
    r"TELEGRAM_BOT_TOKEN\s*=\s*\S+",
    r"OPENAI_(API_KEY|AUTH_TOKEN)\s*=\s*\S+",
    r"ANTHROPIC_API_KEY\s*=\s*\S+",
    r"GOOGLE_API_KEY\s*=\s*\S+",
    r"BEGIN [A-Z ]*PRIVATE KEY",
    r"\b\d{8,10}:[A-Za-z0-9_-]{20,}\b",
    r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[0-1]))\.\d{1,3}\.\d{1,3}\b",
]

_EXAMPLE_MARKERS = (
    "...",
    "…",
    "***",
    "<",
    ">",
    "example",
    "fake",
    "dummy",
    "test",
    "placeholder",
    "your_",
    "your-",
    "foo bar",
    "assertnotin",
    "assertin",
    "write_text",
    "xxx",
    "localhost",
    "127.0.0.1",
)

_PUBLIC_FEATURE_HINTS = {
    "visible_work": ["streaming-contract.md", "TelegramStreamConsumer", "HELLOAGI_TELEGRAM_LIVE"],
    "telegram": ["telegram.py", "docs/channels.md", "HELLOAGI_TELEGRAM_GROUP_MODE"],
    "service": ["service/manager.py", "docs/deployment.md", "helloagi service install"],
    "providers": ["providers.py", "docs/providers.md", "helloagi models"],
    "tools": ["tools/builtins", "helloagi tools", "docs/security.md"],
    "memory": ["memory/", "memory_store", "HELLOAGI_MEMORY_SCOPE"],
    "reminders": ["reminders", "docs/reminders-scheduling.md", "/remind"],
    "runs": ["runs", "helloagi runs", "runs export"],
}


def _run_git(repo: Path, args: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            check=False,
            text=True,
            capture_output=True,
            timeout=20,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def _git_files(repo: Path) -> list[str]:
    code, out = _run_git(repo, ["ls-files"])
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, path, flags=re.IGNORECASE) for pattern in patterns)


def _tracked_runtime_artifacts(repo: Path) -> list[str]:
    return [p for p in _git_files(repo) if _matches_any(p, _RUNTIME_PATTERNS)]


def _check_ignore_rule(repo: Path, rel_path: str) -> bool:
    code, _ = _run_git(repo, ["check-ignore", "-q", rel_path])
    return code == 0


def _scan_private_text(repo: Path, files: list[str]) -> list[str]:
    findings: list[str] = []
    text_suffixes = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".sh", ".ps1", ".ini"}
    for rel in files:
        p = repo / rel
        if p.suffix.lower() not in text_suffixes or not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            stripped = line.strip()
            if rel == "src/agi_runtime/diagnostics/public_readiness.py" and stripped.startswith('r"'):
                continue
            lowered = line.lower()
            if any(marker in lowered for marker in _EXAMPLE_MARKERS):
                continue
            for pattern in _PRIVATE_TEXT_PATTERNS:
                if re.search(pattern, line):
                    findings.append(f"{rel}: matches {pattern}")
                    break
            if findings and findings[-1].startswith(f"{rel}:"):
                break
    return findings[:25]


def _content_index(repo: Path, files: list[str]) -> str:
    parts: list[str] = []
    interesting_suffixes = {".py", ".md", ".toml"}
    for rel in files:
        p = repo / rel
        if p.suffix.lower() in interesting_suffixes and p.is_file():
            try:
                parts.append(rel)
                if p.stat().st_size <= 120_000:
                    parts.append(p.read_text(encoding="utf-8", errors="replace")[:120_000])
            except Exception:
                continue
    return "\n".join(parts)


def run_public_readiness(repo_path: str | os.PathLike[str] = ".", *, require_clean: bool = True) -> dict:
    """Audit whether a checkout is safe and understandable for public users.

    This is intentionally local/static. It does not require network access and never
    prints secrets. It checks the open-source hygiene gates that are easy to regress
    in a live runtime checkout before committing or publishing.
    """
    repo = Path(repo_path).resolve()
    checks: list[PublicReadinessCheck] = []

    code, root_out = _run_git(repo, ["rev-parse", "--show-toplevel"])
    in_git = code == 0
    checks.append(PublicReadinessCheck(
        "git_repository",
        in_git,
        root_out.strip() if in_git else "not a git repository",
        "Run from the HelloAGI repository root." if not in_git else "",
    ))
    if not in_git:
        return _finish(checks)

    git_root = Path(root_out.strip()).resolve()
    files = _git_files(git_root)

    missing_docs = [doc for doc in _REQUIRED_DOCS if not (git_root / doc).is_file()]
    checks.append(PublicReadinessCheck(
        "public_docs",
        not missing_docs,
        "all required public docs present" if not missing_docs else "missing: " + ", ".join(missing_docs),
        "Add or restore the missing docs before publishing." if missing_docs else "",
    ))

    organism_doc = git_root / "docs" / "organism-architecture.md"
    organism_plan = git_root / "docs" / "plans" / "bioagent-organism-intelligence-phases.md"
    organism_missing: list[str] = []
    if not organism_doc.is_file():
        organism_missing.append("docs/organism-architecture.md")
    if not organism_plan.is_file():
        organism_missing.append("docs/plans/bioagent-organism-intelligence-phases.md")
    missing_organs: list[str] = []
    if organism_doc.is_file():
        organism_text = organism_doc.read_text(encoding="utf-8", errors="replace").lower()
        missing_organs = [organ for organ, terms in _ORGANISM_ARCHITECTURE_TERMS.items() if not any(term in organism_text for term in terms)]
    organism_ok = not organism_missing and not missing_organs
    organism_detail = "organ-system architecture docs present and mapped"
    if organism_missing:
        organism_detail = "missing: " + ", ".join(organism_missing)
    elif missing_organs:
        organism_detail = "missing organ coverage: " + ", ".join(missing_organs)
    checks.append(PublicReadinessCheck(
        "organism_architecture",
        organism_ok,
        organism_detail,
        "Add the organism architecture doc/plan and map every organ system to implemented or planned modules." if not organism_ok else "",
    ))

    tracked_runtime = _tracked_runtime_artifacts(git_root)
    tracked_blockers = [p for p in tracked_runtime if p not in _BENIGN_TRACKED_RUNTIME]
    checks.append(PublicReadinessCheck(
        "tracked_runtime_artifacts",
        not tracked_blockers,
        "none" if not tracked_blockers else ", ".join(tracked_blockers[:20]),
        "Untrack runtime state/secrets; keep only .example templates." if tracked_blockers else "",
    ))

    ignore_targets = [
        ".env",
        "helloagi.json",
        "helloagi.onboard.json",
        "memory/identity_state.json",
        "memory/openai_codex_oauth.json",
        "memory/helloagi.db",
        "OPS_STATUS.md",
        "PAUSED_AUTOMATIONS.md",
    ]
    not_ignored = [target for target in ignore_targets if not _check_ignore_rule(git_root, target)]
    checks.append(PublicReadinessCheck(
        "private_artifact_ignores",
        not not_ignored,
        "all private/runtime targets ignored" if not not_ignored else "not ignored: " + ", ".join(not_ignored),
        "Patch .gitignore so runtime state cannot be added accidentally." if not_ignored else "",
    ))

    private_findings = _scan_private_text(git_root, files)
    checks.append(PublicReadinessCheck(
        "private_text_scan",
        not private_findings,
        "no obvious private tokens, IPs, or chat IDs in tracked text" if not private_findings else "; ".join(private_findings),
        "Remove private values or replace with clearly fake examples." if private_findings else "",
    ))

    pyproject = git_root / "pyproject.toml"
    readme = git_root / "README.md"
    scripts_ok = (git_root / "scripts" / "install.sh").is_file() and (git_root / "scripts" / "install.ps1").is_file()
    package_ok = pyproject.is_file() and readme.is_file() and scripts_ok
    checks.append(PublicReadinessCheck(
        "install_entrypoints",
        package_ok,
        "pyproject, README, Unix and Windows installers present" if package_ok else "missing packaging/readme/install script",
        "Keep PyPI metadata, README, and cross-platform installers in sync." if not package_ok else "",
    ))

    tests_present = any(p.startswith("tests/") and p.endswith(".py") for p in files)
    checks.append(PublicReadinessCheck(
        "tests_present",
        tests_present,
        "tracked pytest suite present" if tests_present else "no tracked tests found",
        "Add pytest coverage for public runtime features." if not tests_present else "",
    ))

    index = _content_index(git_root, files)
    missing_features = [name for name, hints in _PUBLIC_FEATURE_HINTS.items() if not any(hint in index for hint in hints)]
    checks.append(PublicReadinessCheck(
        "user_runtime_features_documented",
        not missing_features,
        "visible work, channels, service, providers, tools, memory, reminders, and runs are documented/discoverable"
        if not missing_features else "missing/disconnected: " + ", ".join(missing_features),
        "Document and expose missing user-facing runtime features." if missing_features else "",
    ))

    if require_clean:
        code, status = _run_git(git_root, ["status", "--short", "--untracked-files=all"])
        dirty_lines = [line for line in status.splitlines() if line.strip()]
        checks.append(PublicReadinessCheck(
            "working_tree_clean_for_release",
            not dirty_lines,
            "clean" if not dirty_lines else f"{len(dirty_lines)} local changes/untracked files",
            "Commit intentional changes and keep runtime artifacts ignored before release." if dirty_lines else "",
        ))
    else:
        checks.append(PublicReadinessCheck(
            "working_tree_clean_for_release",
            True,
            "skipped because require_clean=False",
            "",
        ))

    return _finish(checks)


def _finish(checks: list[PublicReadinessCheck]) -> dict:
    passed = sum(1 for c in checks if c.ok)
    total = len(checks)
    grade = round((passed / total) * 100) if total else 0
    blockers = [c.name for c in checks if not c.ok]
    return {
        "grade": grade,
        "passed": passed,
        "total": total,
        "ready": not blockers,
        "blockers": blockers,
        "checks": [asdict(c) for c in checks],
    }


def format_public_readiness(report: dict) -> str:
    status = "READY" if report.get("ready") else "NEEDS WORK"
    lines = [
        f"HelloAGI public readiness: {status}",
        f"Score: {report.get('grade', 0)} ({report.get('passed', 0)}/{report.get('total', 0)} checks)",
    ]
    blockers = report.get("blockers") or []
    if blockers:
        lines.append("Blockers: " + ", ".join(blockers))
    lines.append("")
    for check in report.get("checks", []):
        icon = "✓" if check.get("ok") else "✗"
        lines.append(f"{icon} {check.get('name')}: {check.get('detail')}")
        if not check.get("ok") and check.get("action"):
            lines.append(f"  action: {check['action']}")
    return "\n".join(lines)
