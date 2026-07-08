from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "audio-meeting-minutes" / "scripts" / "transcribe_meeting_audio.py"


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


if __name__ == "__main__":
    for test in [
        test_assign_speakers_aggregates_overlap_by_speaker_and_rejects_weak_coverage,
        test_group_turns_preserves_lowest_confidence_and_splits_long_turns,
        test_heuristic_requires_positive_speaker_count_and_uses_turn_labels,
        test_source_identifier_redacts_full_path_and_markdown_cell_is_safe,
    ]:
        test()
    print("PASS")
