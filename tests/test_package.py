import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PluginPackageTests(unittest.TestCase):
    def test_manifest_exposes_the_existing_skill(self) -> None:
        manifest_path = ROOT / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "audio-meeting-minutes")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(
            manifest["repository"],
            "https://github.com/leopardneko89-crypto/audio-meeting-minutes-skill",
        )
        self.assertTrue((ROOT / "skills" / "audio-meeting-minutes" / "SKILL.md").is_file())
        self.assertFalse((ROOT / "audio-meeting-minutes").exists())

    def test_workflow_runs_official_plugin_validation(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validate_plugin.py", workflow)
        self.assertIn(
            "ebda00d55d7518b127f675f062fb5c6e7a1ffdc0a99df1a55ac594400d7d3228",
            workflow,
        )
        self.assertIn('python-version: "3.12.10"', workflow)
        self.assertIn("ubuntu-24.04", workflow)
        self.assertIn("windows-2025", workflow)
        self.assertIn("skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py", workflow)


if __name__ == "__main__":
    unittest.main()
