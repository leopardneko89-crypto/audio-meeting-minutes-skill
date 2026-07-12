import importlib.util
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "audio-meeting-minutes" / "scripts" / "transcribe_meeting_audio.py"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("transcribe_meeting_audio", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assign_speakers_aggregates_overlap_by_speaker_and_rejects_weak_coverage():
    module = load_module()
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "long utterance"},
        {"start": 10.0, "end": 14.0, "text": "weak overlap"},
    ]
    speaker_turns = [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
        {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        {"start": 2.0, "end": 2.5, "speaker": "SPEAKER_02"},
        {"start": 10.0, "end": 10.4, "speaker": "SPEAKER_03"},
    ]

    assigned = module.assign_speakers(transcript, speaker_turns)

    assert assigned[0]["speaker"] == "SPEAKER_01"
    assert assigned[0]["speaker_confidence"] == "high"
    assert assigned[1]["speaker"] == "UNKNOWN"
    assert assigned[1]["speaker_confidence"] == "low-coverage"


def test_group_turns_preserves_lowest_confidence_and_splits_long_turns():
    module = load_module()
    segments = [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "speaker_confidence": "high", "text": "first"},
        {"start": 1.1, "end": 2.0, "speaker": "SPEAKER_01", "speaker_confidence": "low", "text": "second"},
        {"start": 2.1, "end": 3.0, "speaker": "SPEAKER_01", "speaker_confidence": "high", "text": "third"},
    ]

    turns = module.group_turns(segments, pause_threshold=1.0, max_turn_duration=2.0)

    assert len(turns) == 2
    assert turns[0]["text"] == "first second"
    assert turns[0]["speaker_confidence"] == "low"
    assert turns[1]["text"] == "third"


def test_heuristic_requires_positive_speaker_count_and_uses_turn_labels():
    module = load_module()

    try:
        module.validate_options(
            speaker_mode="heuristic",
            speakers=0,
            pause_threshold=1.0,
            max_turn_duration=45.0,
        )
    except ValueError as exc:
        assert "speakers" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    labeled = module.apply_heuristic_turn_labels(
        [
            {"start": 0.0, "end": 1.0, "text": "question"},
            {"start": 3.0, "end": 4.0, "text": "answer"},
        ],
        speakers=2,
        pause_threshold=1.0,
    )

    assert labeled[0]["speaker"] == "TURN_01"
    assert labeled[1]["speaker"] == "TURN_02"
    assert labeled[0]["speaker_confidence"] == "heuristic-low"


def test_source_identifier_redacts_full_path_and_markdown_cell_is_safe():
    module = load_module()

    identifier = module.source_identifier(Path("/Users/jay/Private Client/secret meeting.m4a"), "abcdef123456")
    assert identifier["filename"] == "secret meeting.m4a"
    assert identifier["sha256_prefix"] == "abcdef123456"
    assert "Private Client" not in str(identifier)
    assert "/Users/jay" not in str(identifier)

    text = module.markdown_cell("a | b\n<script>x</script>")
    assert "|" not in text
    assert "\n" not in text
    assert "&lt;script&gt;" in text


def test_source_identifier_uses_portable_basename_for_windows_paths():
    module = load_module()

    pure_path_identifier = module.source_identifier(
        PureWindowsPath("X:", "recordings", "secret.m4a"),
        "abcdef123456",
    )
    raw_path_identifier = module.source_identifier(
        r"X:\recordings\secret.m4a",
        "abcdef123456",
    )

    assert pure_path_identifier["filename"] == "secret.m4a"
    assert raw_path_identifier["filename"] == "secret.m4a"
    assert "recordings" not in str(pure_path_identifier)
    assert "recordings" not in str(raw_path_identifier)


def test_tracked_instruction_files_have_no_machine_specific_or_legacy_skill_paths():
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    relevant_suffixes = {".md", ".py", ".yaml", ".yml"}
    relevant_files = [
        ROOT / relative
        for relative in tracked
        if Path(relative).suffix.lower() in relevant_suffixes
        and not Path(relative).parts[0] == "tests"
    ]
    forbidden_patterns = {
        "macOS user home": re.compile(r"/Users/[^/\s`]+"),
        "Windows user home": re.compile(r"(?i)\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s`]+"),
        "legacy Codex skill root": re.compile(r"(?:~|\$HOME)/\.codex/skills"),
    }

    violations = []
    for path in relevant_files:
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(ROOT)}: {label}")

    assert not violations, "\n".join(violations)


def test_readme_uses_current_portable_personal_skill_root():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "$HOME/.agents/skills/audio-meeting-minutes" in readme
    assert "~/.codex/skills" not in readme
    assert "/Users/" not in readme


def test_readme_install_examples_merge_skill_contents_on_rerun():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'cp -R "$SKILL_SOURCE/." "$SKILL_DEST/"' in readme
    assert "Get-ChildItem -LiteralPath $SkillSource -Force" in readme
    assert "Copy-Item -Destination $SkillDest -Recurse -Force" in readme


def test_instruction_commands_use_cross_platform_python_launcher():
    instructions = "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "audio-meeting-minutes" / "SKILL.md").read_text(encoding="utf-8"),
        ]
    )

    assert not re.search(r"(?m)^python3\b", instructions)


def test_agent_default_prompt_preserves_explicit_skill_invocation():
    agent_config = (
        ROOT / "audio-meeting-minutes" / "agents" / "openai.yaml"
    ).read_text(encoding="utf-8")

    assert "$audio-meeting-minutes" in agent_config


def test_self_test_runs_from_checkout_path_with_spaces_and_korean_text():
    with tempfile.TemporaryDirectory() as temp_dir:
        checkout = Path(temp_dir) / "checkout with spaces" / "한글 경로"
        copied_skill = checkout / "audio-meeting-minutes"
        shutil.copytree(ROOT / "audio-meeting-minutes", copied_skill)
        skill_text = (copied_skill / "SKILL.md").read_text(encoding="utf-8")
        relative_contract = Path("references") / "output_contract.md"

        assert relative_contract.as_posix() in skill_text
        contract_text = (copied_skill / relative_contract).read_text(encoding="utf-8")
        assert "Audio Meeting Output Contract" in contract_text

        completed = subprocess.run(
            [
                sys.executable,
                str(copied_skill / "scripts" / "transcribe_meeting_audio.py"),
                "--self-test",
            ],
            cwd=checkout,
            check=False,
            capture_output=True,
            text=True,
        )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "PASS"


def test_ci_runs_pinned_cross_platform_validation_without_credentials():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "timeout-minutes:" in workflow
    assert "PYTHONUTF8:" in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "9e552e9d15ba52bed7077d5357f3e18e330f8f38" in workflow
    assert "6cc9dc3199c935916cf6f73fcbbbb0e3bb1b58c8f5109fefa499978908164f51" in workflow
    assert "quick_validate.py" in workflow
    assert "PyYAML==6.0.3" in workflow
    assert "tests/test_audio_meeting_utils.py" in workflow
    assert "--self-test" in workflow
    assert "git diff --exit-code" in workflow
    assert not re.search(r"(?i)(HF_TOKEN|HUGGINGFACE_TOKEN|OPENAI_API_KEY)\s*:", workflow)


if __name__ == "__main__":
    for test in [
        test_assign_speakers_aggregates_overlap_by_speaker_and_rejects_weak_coverage,
        test_group_turns_preserves_lowest_confidence_and_splits_long_turns,
        test_heuristic_requires_positive_speaker_count_and_uses_turn_labels,
        test_source_identifier_redacts_full_path_and_markdown_cell_is_safe,
        test_source_identifier_uses_portable_basename_for_windows_paths,
        test_tracked_instruction_files_have_no_machine_specific_or_legacy_skill_paths,
        test_readme_uses_current_portable_personal_skill_root,
        test_readme_install_examples_merge_skill_contents_on_rerun,
        test_instruction_commands_use_cross_platform_python_launcher,
        test_agent_default_prompt_preserves_explicit_skill_invocation,
        test_self_test_runs_from_checkout_path_with_spaces_and_korean_text,
        test_ci_runs_pinned_cross_platform_validation_without_credentials,
    ]:
        test()
    print("PASS")
