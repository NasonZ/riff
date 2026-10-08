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
DEFINITION = re.compile(r"^- `(RIF-[A-Z]+-\d{3})` \[([FRT])\]: ", re.MULTILINE)
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
        design = (ROOT / "references" / "DESIGN.md").read_text()
        defined = [match.group(1) for match in DEFINITION.finditer(design)]
        self.assertEqual(len(defined), len(set(defined)), "duplicate rule definitions")
        cited: dict[str, set[str]] = {}
        for path in knowledge_files():
            for rule in RULE_ID.findall(path.read_text()):
                cited.setdefault(rule, set()).add(str(path.relative_to(ROOT)))
        undefined = {rule: sorted(files) for rule, files in cited.items() if rule not in defined}
        self.assertEqual(undefined, {}, "cited rule IDs missing from DESIGN.md")

    def test_documented_requests_are_valid_and_warning_free(self) -> None:
        for name in ("SKILL.md", "README.md", "references/PROTOCOLS.md"):
            blocks = re.findall(r"```json\n(.*?)\n```", (ROOT / name).read_text(), re.DOTALL)
            self.assertTrue(blocks, f"{name} must show a request example")
            for index, block in enumerate(blocks):
                with self.subTest(document=name, example=index), tempfile.TemporaryDirectory() as cwd:
                    value = json.loads(block)
                    for participant in value["participants"]:
                        participant["cwd"] = cwd
                    request = RunRequest.from_dict(value)
                    self.assertEqual(request_warnings(request), [])

    def test_skill_body_stays_under_the_documented_line_limit(self) -> None:
        body = (ROOT / "SKILL.md").read_text().split("---", 2)[2]
        self.assertLess(len(body.splitlines()), 500)  # Anthropic skill-authoring guidance

    def test_skill_links_every_reference_directly(self) -> None:
        # Anthropic's guidance keeps references one level deep: an agent may only
        # partly read a file reached through another reference.
        links = LOCAL_LINK.findall((ROOT / "SKILL.md").read_text())
        for link in links:
            self.assertTrue((ROOT / link).is_file(), f"SKILL.md links to missing {link}")
        linked = {(ROOT / link).resolve() for link in links}
        for path in sorted((ROOT / "references").glob("*.md")):
            self.assertIn(path.resolve(), linked, f"SKILL.md does not link {path.name}")

    def test_long_references_open_with_contents(self) -> None:
        for path in sorted((ROOT / "references").glob("*.md")):
            text = path.read_text()
            if len(text.splitlines()) > 100 and path.name != "NOTES.md":
                self.assertIn("## Contents", text[:1500], f"{path.name} needs a table of contents")

    def test_forward_test_datasets_are_usable(self) -> None:
        triggers = json.loads((ROOT / "tests" / "trigger_cases.json").read_text())
        positive, negative = triggers["should_trigger"], triggers["should_not_trigger"]
        prompts = [case["prompt"] for case in positive + negative]
        self.assertEqual(len(prompts), len(set(prompts)), "duplicate trigger prompts")
        self.assertTrue(positive and negative, "triggers need both sides")
        # near-misses share vocabulary with real triggers; they are the informative negatives
        self.assertGreater(sum(bool(case.get("near_miss")) for case in negative), len(negative) // 2)

        behaviors = json.loads((ROOT / "tests" / "behavior_cases.json").read_text())["cases"]
        design = (ROOT / "references" / "DESIGN.md").read_text()
        defined = {match.group(1) for match in DEFINITION.finditer(design)}
        for case in behaviors:
            with self.subTest(case["id"]):
                self.assertIn(case["rule"], defined)
                self.assertTrue(case["query"].strip())
                self.assertGreaterEqual(len(case["expected_behavior"]), 2)

if __name__ == "__main__":
    unittest.main()
