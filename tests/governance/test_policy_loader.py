"""PolicyLoader tests — declarative .srgpolicy/*.md files extend SRG.

These tests pin:

1. A single project-layer file extends the base Policy's deny/escalate
   lists while preserving existing entries.
2. ``merge: replace`` clobbers a list instead of appending.
3. Allow-list enforcement — unknown frontmatter keys are silently
   ignored rather than injecting into the Policy.
4. Multiple layers compose in `managed > user > project` order.
5. ``maybe_reload`` picks up mtime changes and reports ``changed``.
6. Composed Policy is a clone — composing never mutates the original
   Policy passed in.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from agi_runtime.governance.policy_loader import PolicyLoader
from agi_runtime.governance.srg import Policy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestSingleProjectFile(unittest.TestCase):
    def test_extend_merges_into_base_policy(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "finance.md", (
                "---\n"
                "name: finance\n"
                "merge: extend\n"
                "deny_keywords:\n"
                "  - \"wire transfer\"\n"
                "  - \"sign-off\"\n"
                "escalate_keywords:\n"
                "  - \"SOX\"\n"
                "---\n"
                "# finance policy\n"
            ))
            loader = PolicyLoader(roots={"project": d})
            policy = loader.compose(onto=Policy())
            self.assertIn("wire transfer", policy.deny_keywords)
            self.assertIn("sign-off", policy.deny_keywords)
            self.assertIn("SOX", policy.escalate_keywords)
            # Base policy entries survive.
            self.assertIn("harm", policy.deny_keywords)
            self.assertIn("finance", policy.escalate_keywords)


class TestReplaceSemantics(unittest.TestCase):
    def test_replace_clobbers_base_deny_list(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "strict.md", (
                "---\n"
                "name: strict\n"
                "merge: replace\n"
                "deny_keywords:\n"
                "  - \"only-this-one-thing\"\n"
                "---\n"
            ))
            loader = PolicyLoader(roots={"project": d})
            policy = loader.compose(onto=Policy())
            self.assertEqual(policy.deny_keywords, ["only-this-one-thing"])
            # Base policy's other lists are untouched.
            self.assertIn("finance", policy.escalate_keywords)


class TestAllowListEnforcement(unittest.TestCase):
    def test_unknown_field_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "bad.md", (
                "---\n"
                "name: bad\n"
                "max_risk_allow: 0.99\n"  # Not in the allow-list.
                "sudo_sauce: 1\n"         # Garbage.
                "deny_keywords:\n"
                "  - \"secret-one\"\n"
                "---\n"
            ))
            loader = PolicyLoader(roots={"project": d})
            policy = loader.compose(onto=Policy())
            # Legitimate key still applies.
            self.assertIn("secret-one", policy.deny_keywords)
            # Bogus keys must NOT have bled into the Policy.
            self.assertAlmostEqual(policy.max_risk_allow, 0.45)
            self.assertFalse(hasattr(policy, "sudo_sauce"))


class TestLayerOrdering(unittest.TestCase):
    def test_managed_user_project_compose_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            managed = Path(root) / "managed"
            user = Path(root) / "user"
            project = Path(root) / "project"
            _write(managed / "m.md", (
                "---\nname: m\ndeny_keywords:\n  - \"m-deny\"\n---\n"
            ))
            _write(user / "u.md", (
                "---\nname: u\ndeny_keywords:\n  - \"u-deny\"\n---\n"
            ))
            _write(project / "p.md", (
                "---\nname: p\ndeny_keywords:\n  - \"p-deny\"\n---\n"
            ))
            loader = PolicyLoader(roots={
                "managed": str(managed),
                "user": str(user),
                "project": str(project),
            })
            policy = loader.compose(onto=Policy())
            # All three layers contributed.
            for kw in ("m-deny", "u-deny", "p-deny"):
                self.assertIn(kw, policy.deny_keywords)
            # Order is preserved — managed keys appear before project keys
            # in the final list (extend merge, managed loaded first).
            self.assertLess(
                policy.deny_keywords.index("m-deny"),
                policy.deny_keywords.index("p-deny"),
            )


class TestMaybeReload(unittest.TestCase):
    def test_mtime_change_triggers_reload(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "live.md"
            _write(p, (
                "---\nname: live\ndeny_keywords:\n  - \"v1\"\n---\n"
            ))
            loader = PolicyLoader(roots={"project": d})
            loader.load_all()
            state, changed = loader.maybe_reload()
            self.assertFalse(changed)
            policy_v1 = loader.compose(onto=Policy())
            self.assertIn("v1", policy_v1.deny_keywords)
            self.assertNotIn("v2", policy_v1.deny_keywords)

            # Bump mtime and content. Use an explicit mtime bump so the
            # test is robust on filesystems with coarse mtime resolution
            # (e.g., some Windows volumes at 2s granularity).
            _write(p, (
                "---\nname: live\ndeny_keywords:\n  - \"v2\"\n---\n"
            ))
            bumped = time.time() + 60
            os.utime(p, (bumped, bumped))
            _, changed = loader.maybe_reload()
            self.assertTrue(changed)
            policy_v2 = loader.compose(onto=Policy())
            self.assertIn("v2", policy_v2.deny_keywords)


class TestIsolation(unittest.TestCase):
    def test_compose_does_not_mutate_input_policy(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "p.md", (
                "---\nname: p\ndeny_keywords:\n  - \"added-from-file\"\n---\n"
            ))
            loader = PolicyLoader(roots={"project": d})
            base = Policy()
            base_original = list(base.deny_keywords)
            _composed = loader.compose(onto=base)
            # The input must be untouched.
            self.assertEqual(base.deny_keywords, base_original)


class TestEmptyRoot(unittest.TestCase):
    def test_no_policy_files_yields_clone_of_base(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            loader = PolicyLoader(roots={"project": d})
            policy = loader.compose(onto=Policy())
            # Clone, not identity — compose() always returns a new object.
            self.assertEqual(policy.deny_keywords, Policy().deny_keywords)


if __name__ == "__main__":
    unittest.main()
