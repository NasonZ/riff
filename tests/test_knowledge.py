"""Invariants of the skill's knowledge layers: identifiers, links, and datasets."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.riff_core.models import RunRequest, request_warnings

ROOT = Path(__file__).resolve().parent.parent
RULE_ID = re.compile(r"RIF-[A-Z]+-\d{3}")
DEFINITION = re.compile(r"^- `(RIF-[A-Z]+-\d{3})` \[([FRT])\] — ", re.M)
LOCAL_LINK = re.compile(r"\]\(((?!https?:)[^)#]+)(?:#[^)]*)?\)")


def knowledge_files() -> list[Path]:
    return [
        path
        for path in [ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "references").glob("*.md"))]
        + sorted((ROOT / "scripts").rglob("*.py"))
        + sorted((ROOT / "tests").glob("*.json"))
        if "__pycache__" not in path.parts
    ]


class KnowledgeTests(unittest.TestCase):
    def test_every_cited_rule_id_is_defined_once_with_a_basis(self) -> None:
        playbook = (ROOT / "references" / "PLAYBOOK.md").read_text()
        defined = [match.group(1) for match in DEFINITION.finditer(playbook)]
        self.assertEqual(len(defined), len(set(defined)), "duplicate rule definitions")
        cited: dict[str, set[str]] = {}
        for path in knowledge_files():
            for rule in RULE_ID.findall(path.read_text()):
                cited.setdefault(rule, set()).add(str(path.relative_to(ROOT)))
        undefined = {rule: sorted(files) for rule, files in cited.items() if rule not in defined}
        self.assertEqual(undefined, {}, "cited rule IDs missing from PLAYBOOK.md")

    def test_skill_example_request_is_valid_and_warning_free(self) -> None:
        skill = (ROOT / "SKILL.md").read_text()
        block = re.search(r"```json\n(.*?)\n```", skill, re.S)
        self.assertIsNotNone(block, "SKILL.md must show a request example")
        value = json.loads(block.group(1))
        with tempfile.TemporaryDirectory() as cwd:
            for participant in value["participants"]:
                participant["cwd"] = cwd
            request = RunRequest.from_dict(value)
            self.assertEqual(request_warnings(request), [])

    def test_skill_body_stays_within_budget(self) -> None:
        body = (ROOT / "SKILL.md").read_text().split("---", 2)[2]
        self.assertLess(len(body.splitlines()), 500)
        self.assertLess(len(body.split()), 2000)

    def test_skill_links_resolve_and_stay_one_level_deep(self) -> None:
        for link in LOCAL_LINK.findall((ROOT / "SKILL.md").read_text()):
            target = ROOT / link
            self.assertTrue(target.is_file(), f"SKILL.md links to missing {link}")
            self.assertLessEqual(len(Path(link).parts), 2, f"{link} is nested too deeply")

    def test_long_references_open_with_contents(self) -> None:
        for path in sorted((ROOT / "references").glob("*.md")):
            text = path.read_text()
            if len(text.splitlines()) > 100 and path.name != "NOTES.md":
                self.assertIn("## Contents", text[:1500], f"{path.name} needs a table of contents")

    def test_trigger_cases_cover_both_sides_with_near_misses(self) -> None:
        cases = json.loads((ROOT / "tests" / "trigger_cases.json").read_text())
        positive, negative = cases["should_trigger"], cases["should_not_trigger"]
        self.assertGreaterEqual(len(positive), 8)
        self.assertGreaterEqual(len(negative), 8)
        prompts = [case["prompt"] for case in positive + negative]
        self.assertEqual(len(prompts), len(set(prompts)), "duplicate trigger prompts")
        self.assertTrue(
            any(case.get("near_miss") for case in negative),
            "negatives need near-misses that share vocabulary with real triggers",
        )

    def test_behavior_cases_name_a_rule_and_observable_expectations(self) -> None:
        cases = json.loads((ROOT / "tests" / "behavior_cases.json").read_text())
        playbook = (ROOT / "references" / "PLAYBOOK.md").read_text()
        defined = {match.group(1) for match in DEFINITION.finditer(playbook)}
        for case in cases["cases"]:
            self.assertIn(case["rule"], defined, f"{case['id']} cites an undefined rule")
            self.assertTrue(case["query"].strip())
            self.assertGreaterEqual(len(case["expected_behavior"]), 2, case["id"])


if __name__ == "__main__":
    unittest.main()
