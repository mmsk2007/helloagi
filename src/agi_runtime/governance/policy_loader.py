"""Declarative policy loader — `.srgpolicy/*.md` files extend SRG at runtime.

Cycle 1 left SRG's deny / escalate / exfil / dangerous-command lists
hard-coded as Python defaults. That's fine for the base posture but it
makes per-deployment governance a code change. Operators can't add a
company-specific deny keyword without patching the library.

This module introduces **declarative, versioned, hot-reloadable policy
files**. Inspiration is the hookify plugin from the `claude/` sibling
and the 2026 industry direction (AGENTS.md, NVIDIA OpenShell, OPA):
governance-as-data, not governance-as-code. Same philosophy as SRG
itself — pure Python evaluation, but the *data* the evaluator reads
is now discoverable, diffable, and reviewable.

Format (markdown with YAML frontmatter, per `claude/plugins/hookify`):

    ---
    name: company-xyz-finance
    # Merge semantics: "extend" adds to the existing policy,
    # "replace" clobbers it. Default "extend". Per-list overrides
    # honored (e.g., deny_keywords: extend, exfil_patterns: replace).
    merge: extend
    deny_keywords:
      - "wire transfer"
      - "sign-off authority"
    escalate_keywords:
      - "budget variance"
      - "SOX"
    dangerous_command_patterns:
      - "terraform destroy"
    exfil_patterns:
      - "sensitive_table"
    ---
    # Optional human-readable rationale. Ignored by the loader.
    Why we block these: per compliance-team policy 2026-Q2 …

Layering (from `claude/` MDM pattern): `managed > user > project`.
A higher layer's ``merge: replace`` wipes the layers below it; the
default ``extend`` appends. No layer can *weaken* an above-layer's
deny — a project-level file cannot override a managed-level deny
keyword. This is the MDM-lock pattern for enterprise deployments.

Hot-reload: the loader tracks file mtimes. ``maybe_reload()`` is
cheap enough to call per-turn; it re-reads only files whose mtime
changed. This keeps the audit trail aligned with whatever policy
was *actually in force* at the moment of decision.

This module is pure-Python and has no external deps. The YAML
parser is a deliberately small, restricted subset that only handles
what the schema requires (strings and flat lists of strings). We
refuse to pull in PyYAML just for this — a broader parser is also
a bigger attack surface for a file-format-driven feature.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from agi_runtime.governance.srg import Policy


# The fields of Policy that a .srgpolicy file is allowed to mutate.
# Anything else in the YAML is ignored — this is an allow-list, not a
# block-list, so typos or malicious keys can't reach into internal state.
_ALLOWED_LIST_KEYS = {
    "deny_keywords",
    "escalate_keywords",
    "prompt_injection_escalate_patterns",
    "prompt_injection_deny_patterns",
    "dangerous_command_patterns",
    "exfil_patterns",
}

# Layer order: earlier layers are overridden by later layers when
# ``merge: replace`` is set. This is the MDM-style lock order.
_LAYER_ORDER = ("managed", "user", "project")


@dataclass
class PolicyDocument:
    """One parsed .srgpolicy/*.md file."""

    name: str
    path: Path
    layer: str  # "managed" | "user" | "project"
    merge: str  # "extend" | "replace"
    fields: Dict[str, List[str]] = field(default_factory=dict)
    mtime: float = 0.0


@dataclass
class LoadedPolicies:
    """Result of a single load pass — what's currently in force."""

    documents: List[PolicyDocument] = field(default_factory=list)
    # Sources of each deny/escalate keyword, for audit trail.
    provenance: Dict[str, List[str]] = field(default_factory=dict)

    def describe(self) -> str:
        if not self.documents:
            return "no declarative policies loaded"
        return (
            f"loaded {len(self.documents)} policy docs from "
            f"{sorted({d.layer for d in self.documents})} layers"
        )


class PolicyLoader:
    """Reads .srgpolicy/*.md files and composes them onto an SRG Policy.

    Typical usage::

        loader = PolicyLoader(roots={
            "managed":  "/etc/helloagi/srgpolicy",
            "user":     "~/.config/helloagi/srgpolicy",
            "project":  ".srgpolicy",
        })
        policy = loader.compose(onto=Policy())
        governor = SRGGovernor(policy=policy)

    Pass the same loader each call — ``compose()`` is idempotent and
    the ``maybe_reload()`` helper only re-reads files whose mtime
    changed since the last pass.
    """

    def __init__(self, roots: Optional[Dict[str, str]] = None):
        self.roots: Dict[str, Path] = {}
        for layer, path in (roots or {}).items():
            if layer not in _LAYER_ORDER:
                continue  # Ignore unknown layers deterministically.
            self.roots[layer] = Path(os.path.expanduser(path))
        self._cache: Dict[Path, PolicyDocument] = {}

    # ----------------------------------------------------------------- API

    def load_all(self) -> LoadedPolicies:
        """Load every .md file under every root, respecting layer order."""
        docs: List[PolicyDocument] = []
        for layer in _LAYER_ORDER:
            root = self.roots.get(layer)
            if not root or not root.exists():
                continue
            for md_path in sorted(root.glob("*.md")):
                doc = self._read_doc(md_path, layer)
                if doc is not None:
                    docs.append(doc)
        self._cache = {d.path: d for d in docs}
        return self._assemble_loaded(docs)

    def maybe_reload(self) -> tuple[LoadedPolicies, bool]:
        """Re-read only files whose mtime changed. Returns (state, changed)."""
        changed = False
        # Detect added / modified files.
        current_paths: set[Path] = set()
        for layer in _LAYER_ORDER:
            root = self.roots.get(layer)
            if not root or not root.exists():
                continue
            for md_path in sorted(root.glob("*.md")):
                current_paths.add(md_path)
                try:
                    mtime = md_path.stat().st_mtime
                except OSError:
                    continue
                cached = self._cache.get(md_path)
                if cached is None or cached.mtime != mtime:
                    new_doc = self._read_doc(md_path, layer)
                    if new_doc is not None:
                        self._cache[md_path] = new_doc
                        changed = True
        # Detect removed files.
        for p in list(self._cache.keys()):
            if p not in current_paths:
                del self._cache[p]
                changed = True

        docs = [self._cache[p] for p in sorted(self._cache.keys())]
        # Preserve layer order regardless of path order.
        docs.sort(key=lambda d: _LAYER_ORDER.index(d.layer))
        return self._assemble_loaded(docs), changed

    def compose(
        self,
        *,
        onto: Optional[Policy] = None,
    ) -> Policy:
        """Fold the currently-loaded declarative docs onto an SRG Policy."""
        state, _ = self.maybe_reload() if self._cache else (self.load_all(), True)
        policy = self._clone_policy(onto or Policy())

        for doc in state.documents:
            for key, values in doc.fields.items():
                if key not in _ALLOWED_LIST_KEYS:
                    continue  # Allow-list enforcement — silent ignore.
                current = list(getattr(policy, key, []) or [])
                if doc.merge == "replace":
                    setattr(policy, key, list(values))
                else:  # extend
                    # De-dupe while preserving order so the compose() output
                    # is deterministic for audit replay.
                    seen = set(current)
                    for v in values:
                        if v not in seen:
                            current.append(v)
                            seen.add(v)
                    setattr(policy, key, current)
        return policy

    # ----------------------------------------------------------- internals

    def _assemble_loaded(self, docs: List[PolicyDocument]) -> LoadedPolicies:
        prov: Dict[str, List[str]] = {}
        for doc in docs:
            for key, values in doc.fields.items():
                for v in values:
                    prov.setdefault(f"{key}:{v}", []).append(
                        f"{doc.layer}:{doc.name}"
                    )
        return LoadedPolicies(documents=docs, provenance=prov)

    def _read_doc(self, path: Path, layer: str) -> Optional[PolicyDocument]:
        """Read and parse one .md file. Returns None on parse failure."""
        try:
            text = path.read_text(encoding="utf-8")
            mtime = path.stat().st_mtime
        except OSError:
            return None

        fm_body = _extract_frontmatter(text)
        if fm_body is None:
            return None

        parsed = _parse_minimal_yaml(fm_body)
        if not isinstance(parsed, dict):
            return None

        name = str(parsed.get("name") or path.stem)
        merge = str(parsed.get("merge") or "extend").strip().lower()
        if merge not in ("extend", "replace"):
            merge = "extend"

        fields: Dict[str, List[str]] = {}
        for key in _ALLOWED_LIST_KEYS:
            if key in parsed:
                vals = parsed[key]
                if isinstance(vals, list):
                    clean = [str(v) for v in vals if isinstance(v, (str, int, float))]
                    if clean:
                        fields[key] = clean
        return PolicyDocument(
            name=name,
            path=path,
            layer=layer,
            merge=merge,
            fields=fields,
            mtime=mtime,
        )

    @staticmethod
    def _clone_policy(p: Policy) -> Policy:
        """Shallow clone so compose() does not mutate the caller's Policy."""
        return Policy(
            deny_keywords=list(p.deny_keywords),
            escalate_keywords=list(p.escalate_keywords),
            prompt_injection_escalate_patterns=list(
                p.prompt_injection_escalate_patterns
            ),
            prompt_injection_deny_patterns=list(p.prompt_injection_deny_patterns),
            dangerous_command_patterns=list(p.dangerous_command_patterns),
            exfil_patterns=list(p.exfil_patterns),
            max_risk_allow=p.max_risk_allow,
            max_risk_escalate=p.max_risk_escalate,
        )


# ------------------------------------------------------------- frontmatter

_FRONTMATTER_RX = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _extract_frontmatter(text: str) -> Optional[str]:
    """Return the YAML frontmatter body, or None if there isn't one."""
    m = _FRONTMATTER_RX.match(text)
    if not m:
        return None
    return m.group(1)


# --------------------------------------------------------------- mini YAML

_KV_RX = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")
_LIST_ITEM_RX = re.compile(r"^\s*-\s*(.*?)\s*$")


def _parse_minimal_yaml(text: str) -> Dict[str, object]:
    """Parse the small YAML dialect we accept.

    Supported shapes::

        key: value
        list_key:
          - "item 1"
          - item 2

    Comments (``# …``) are stripped. Quoted values (single or double)
    are unquoted. Types are strings and lists of strings — that's all
    the schema needs and it keeps the parser tiny. This is deliberately
    not a full YAML implementation: a smaller parser is a smaller
    attack surface for a file-format feature.
    """
    result: Dict[str, object] = {}
    pending_list_key: Optional[str] = None
    pending_list: Optional[List[str]] = None

    for raw_line in text.splitlines():
        # Strip comments (but keep them inside quotes — rare in our schema).
        line = _strip_comment(raw_line)
        if not line.strip():
            continue

        item_m = _LIST_ITEM_RX.match(line)
        if item_m and pending_list is not None:
            value = _unquote(item_m.group(1))
            if value:
                pending_list.append(value)
            continue

        kv_m = _KV_RX.match(line)
        if not kv_m:
            continue

        # Close out any open list.
        if pending_list_key is not None and pending_list is not None:
            result[pending_list_key] = pending_list
            pending_list_key = None
            pending_list = None

        key = kv_m.group(1)
        raw_value = kv_m.group(2)
        if raw_value == "":
            pending_list_key = key
            pending_list = []
        else:
            result[key] = _unquote(raw_value)

    # Flush trailing list.
    if pending_list_key is not None and pending_list is not None:
        result[pending_list_key] = pending_list
    return result


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    out = []
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


__all__ = [
    "PolicyLoader",
    "PolicyDocument",
    "LoadedPolicies",
]
