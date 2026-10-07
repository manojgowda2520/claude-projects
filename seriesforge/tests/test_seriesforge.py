"""Run with: python -m pytest, or plain `python tests/test_seriesforge.py`."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seriesforge import fountain
from seriesforge.cli import main
from seriesforge.errors import SeriesForgeError
from seriesforge.store import Project, format_code, parse_code


class TempProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.previous = os.getcwd()
        os.chdir(self.root)
        os.environ.pop("SERIESFORGE_PROJECT", None)

    def tearDown(self):
        os.chdir(self.previous)
        self.tmp.cleanup()

    def run_cli(self, *argv):
        return main(list(argv))


class TestCodes(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_code("S1E2"), (1, 2))
        self.assertEqual(parse_code("s01e02"), (1, 2))
        self.assertEqual(format_code(1, 2), "S01E02")

    def test_bad_code(self):
        with self.assertRaises(SeriesForgeError):
            parse_code("pilot")


class TestWorkflow(TempProject):
    def build(self):
        self.run_cli("init", "Signal Loss", "--genre", "thriller", "--minutes", "45")
        self.run_cli("character", "add", "MARA", "--role", "lead", "--want", "the truth")
        self.run_cli("character", "add", "DEV", "--role", "foil")
        self.run_cli("thread", "add", "the-tape", "--name", "The tape")
        self.run_cli("episode", "add", "S1E1", "--title", "Static", "--logline", "A signal returns.")
        self.run_cli("beats", "S1E1", "--structure", "five-act")
        self.run_cli("scene", "add", "S1E1", "INT. STATION - NIGHT",
                     "--summary", "Mara hears it", "--characters", "MARA,DEV",
                     "--thread", "the-tape")

    def test_end_to_end(self):
        self.build()
        project = Project.load()
        self.assertEqual(project.data["title"], "Signal Loss")
        episode = project.episode("S1E1")
        self.assertEqual(len(episode["beats"]), 6)
        self.assertEqual(episode["scenes"][0]["characters"], ["MARA", "DEV"])
        self.assertEqual(self.run_cli("draft", "S1E1"), 0)
        self.assertTrue((self.root / "drafts" / "S01E01.fountain").is_file())
        self.assertEqual(self.run_cli("status"), 0)
        self.assertEqual(self.run_cli("stats"), 0)

    def test_duplicate_episode_is_an_error(self):
        self.build()
        self.assertEqual(self.run_cli("episode", "add", "S1E1"), 2)

    def test_draft_is_not_clobbered(self):
        self.build()
        self.run_cli("draft", "S1E1")
        path = self.root / "drafts" / "S01E01.fountain"
        path.write_text("mine", encoding="utf-8")
        self.assertEqual(self.run_cli("draft", "S1E1"), 2)
        self.assertEqual(path.read_text(encoding="utf-8"), "mine")
        self.assertEqual(self.run_cli("draft", "S1E1", "--force"), 0)
        self.assertNotEqual(path.read_text(encoding="utf-8"), "mine")

    def test_scene_reordering_renumbers(self):
        self.build()
        self.run_cli("scene", "add", "S1E1", "EXT. PIER - DAY", "--characters", "MARA")
        self.run_cli("scene", "move", "S1E1", "2", "1")
        scenes = Project.load().episode("S1E1")["scenes"]
        self.assertEqual([s["slug"] for s in scenes],
                         ["EXT. PIER - DAY", "INT. STATION - NIGHT"])
        self.assertEqual([s["n"] for s in scenes], [1, 2])

    def test_continuity_flags_unknown_character(self):
        self.build()
        project = Project.load()
        project.episode("S1E1")["scenes"][0]["characters"].append("GHOST")
        project.save()
        problems = __import__("seriesforge.report", fromlist=["report"]).continuity(project)
        self.assertTrue(any("GHOST" in m for sev, m in problems if sev == "error"))
        self.assertEqual(self.run_cli("continuity"), 1)


class TestFountain(unittest.TestCase):
    SAMPLE = (
        "Title: Static\n"
        "\n"
        "INT. STATION - NIGHT\n"
        "\n"
        "Mara leans into the console.\n"
        "\n"
        "MARA\n"
        "(quiet)\n"
        "Play it again.\n"
        "\n"
        "EXT. PIER - DAY\n"
        "\n"
        "DEV\n"
        "There is nothing on the tape.\n"
    )

    def test_stats(self):
        s = fountain.stats(self.SAMPLE)
        self.assertEqual(s["scenes"], 2)
        self.assertEqual(s["speeches"], 2)
        self.assertEqual(sorted(s["speakers"]), ["DEV", "MARA"])
        self.assertGreater(s["dialogue_words"], 0)
        self.assertGreater(s["action_words"], 0)

    def test_render_indents_dialogue(self):
        text = fountain.render_text(self.SAMPLE)
        lines = text.splitlines()
        self.assertIn(" " * 22 + "MARA", lines)
        self.assertIn(" " * 16 + "(quiet)", lines)
        self.assertIn(" " * 10 + "Play it again.", lines)
        self.assertIn("INT. STATION - NIGHT", lines)

    def test_notes_are_stripped_from_render(self):
        text = fountain.render_text("INT. A - DAY\n\n[[hidden note]]\n\nAction.\n")
        self.assertNotIn("hidden", text)
        self.assertIn("Action.", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
