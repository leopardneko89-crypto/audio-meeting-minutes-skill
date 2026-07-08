#!/usr/bin/env python3
"""Transcribe meeting audio and optionally align speaker diarization turns."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def segment_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def confidence_rank(value: str) -> int:
    ranks = {
        "none": 0,
        "low-coverage": 1,
        "mixed": 1,
        "low": 1,
        "heuristic-low": 1,
        "high": 2,
    }
    return ranks.get(value, 0)


def weakest_confidence(values: list[str]) -> str:
    if not values:
        return "none"
    return min(values, key=confidence_rank)


def assign_speakers(
    transcript_segments: list[dict[str, Any]],
    speaker_turns: list[dict[str, Any]],
    min_coverage: float = 0.5,
    min_dominance: float = 0.6,
) -> list[dict[str, Any]]:
    """Assign transcript segments using aggregate overlap per speaker."""
    assigned: list[dict[str, Any]] = []
    for segment in transcript_segments:
        start = float(segment["start"])
        end = float(segment["end"])
        duration = max(end - start, 0.001)
        overlap_by_speaker: dict[str, float] = {}

        for turn in speaker_turns:
            overlap = segment_overlap(
                start,
                end,
                float(turn["start"]),
                float(turn["end"]),
            )
            if overlap > 0:
                speaker = str(turn["speaker"])
                overlap_by_speaker[speaker] = overlap_by_speaker.get(speaker, 0.0) + overlap

        result = dict(segment)
        total_overlap = sum(overlap_by_speaker.values())
        if total_overlap <= 0:
            result["speaker"] = "UNKNOWN"
            result["speaker_confidence"] = "none"
        else:
            best_speaker, best_overlap = max(overlap_by_speaker.items(), key=lambda item: item[1])
            coverage = min(total_overlap / duration, 1.0)
            dominance = best_overlap / total_overlap
            result["speaker_overlap_ratio"] = round(best_overlap / duration, 3)
            result["speaker_coverage_ratio"] = round(coverage, 3)
            result["speaker_dominance_ratio"] = round(dominance, 3)

            if coverage < min_coverage:
                result["speaker"] = "UNKNOWN"
                result["speaker_confidence"] = "low-coverage"
            elif dominance < min_dominance:
                result["speaker"] = "MIXED"
                result["speaker_confidence"] = "mixed"
            else:
                result["speaker"] = best_speaker
                result["speaker_confidence"] = "high" if best_overlap / duration >= min_coverage else "low"
        assigned.append(result)
    return assigned


def group_turns(
    segments: list[dict[str, Any]],
    pause_threshold: float = 1.2,
    max_turn_duration: float = 45.0,
) -> list[dict[str, Any]]:
    """Merge adjacent transcript segments into readable speaker turns."""
    if not segments:
        return []

    sorted_segments = sorted(segments, key=lambda item: (float(item["start"]), float(item["end"])))
    turns: list[dict[str, Any]] = []
    current = {
        "start": float(sorted_segments[0]["start"]),
        "end": float(sorted_segments[0]["end"]),
        "speaker": sorted_segments[0].get("speaker", "UNKNOWN"),
        "text": str(sorted_segments[0].get("text", "")).strip(),
        "speaker_confidence": sorted_segments[0].get("speaker_confidence", "none"),
        "segment_count": 1,
    }

    for segment in sorted_segments[1:]:
        speaker = segment.get("speaker", "UNKNOWN")
        start = float(segment["start"])
        end = float(segment["end"])
        text = str(segment.get("text", "")).strip()
        confidence = str(segment.get("speaker_confidence", "none"))
        gap = start - float(current["end"])

        current_duration_after_merge = end - float(current["start"])
        if (
            speaker == current["speaker"]
            and gap <= pause_threshold
            and current_duration_after_merge <= max_turn_duration
        ):
            current["end"] = end
            current["text"] = " ".join(part for part in [current["text"], text] if part)
            current["speaker_confidence"] = weakest_confidence(
                [str(current.get("speaker_confidence", "none")), confidence]
            )
            current["segment_count"] = int(current["segment_count"]) + 1
        else:
            turns.append(current)
            current = {
                "start": start,
                "end": end,
                "speaker": speaker,
                "text": text,
                "speaker_confidence": confidence,
                "segment_count": 1,
            }

    turns.append(current)
    return turns


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def markdown_cell(value: Any) -> str:
    text = " ".join(str(value).split())
    text = text.replace("|", "/")
    return html.escape(text, quote=False)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_identifier(path: Path, sha256_value: str) -> dict[str, Any]:
    return {
        "filename": path.name,
        "sha256_prefix": sha256_value[:12],
    }


def probe_media(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
    }
    try:
        completed = subprocess.run(
            ["afinfo", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return metadata

    if completed.returncode != 0:
        return metadata

    output = completed.stdout
    duration_match = re.search(r"estimated duration:\s*([0-9.]+)\s*sec", output)
    if duration_match:
        metadata["duration_seconds"] = float(duration_match.group(1))
    format_match = re.search(r"Data format:\s*(.+)", output)
    if format_match:
        metadata["data_format"] = format_match.group(1).strip()
    bit_rate_match = re.search(r"bit rate:\s*([0-9]+)", output)
    if bit_rate_match:
        metadata["bit_rate"] = int(bit_rate_match.group(1))
    return metadata


def make_run_dir(base_dir: Path, audio_path: Path, sha256_value: str, run_id: str | None = None) -> Path:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", audio_path.stem).strip("-") or "audio"
    suffix = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    return base_dir / f"{safe_stem}-{sha256_value[:8]}-{suffix}"


def validate_options(
    speaker_mode: str,
    speakers: int,
    pause_threshold: float,
    max_turn_duration: float,
) -> None:
    if speakers < 0:
        raise ValueError("speakers must be >= 0")
    if pause_threshold <= 0:
        raise ValueError("pause_threshold must be > 0")
    if max_turn_duration <= 0:
        raise ValueError("max_turn_duration must be > 0")
    if speaker_mode == "heuristic" and speakers <= 0:
        raise ValueError("speakers must be > 0 when speaker_mode is heuristic")


def transcribe_with_faster_whisper(
    audio_path: Path,
    language: str | None,
    model_name: str,
    device: str,
    compute_type: str,
    initial_prompt: str | None,
    vad_min_silence_ms: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: faster-whisper. Install it in the active Python "
            "environment with: python3 -m pip install faster-whisper"
        ) from exc

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        task="transcribe",
        beam_size=5,
        best_of=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": vad_min_silence_ms},
        condition_on_previous_text=True,
        initial_prompt=initial_prompt,
        temperature=0.0,
    )
    segments: list[dict[str, Any]] = []
    for segment in segments_iter:
        segments.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "avg_logprob": float(segment.avg_logprob),
                "no_speech_prob": float(segment.no_speech_prob),
            }
        )
    metadata = {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "engine": "faster-whisper",
    }
    return segments, metadata


def diarize_with_pyannote(
    audio_path: Path,
    token: str | None,
    speakers: int | None,
) -> list[dict[str, Any]]:
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio is not installed. Install it and set HF_TOKEN or "
            "HUGGINGFACE_TOKEN for true speaker diarization."
        ) from exc

    auth_token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not auth_token:
        raise RuntimeError("Missing HF_TOKEN or HUGGINGFACE_TOKEN for pyannote diarization.")

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=auth_token)
    kwargs: dict[str, Any] = {}
    if speakers and speakers > 0:
        kwargs["num_speakers"] = speakers
    diarization = pipeline(str(audio_path), **kwargs)

    turns: list[dict[str, Any]] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append({"start": float(turn.start), "end": float(turn.end), "speaker": str(speaker)})
    return turns


def apply_heuristic_turn_labels(
    segments: list[dict[str, Any]],
    speakers: int,
    pause_threshold: float,
) -> list[dict[str, Any]]:
    """Assign low-confidence alternating labels by long pauses only."""
    if speakers <= 0:
        raise ValueError("speakers must be > 0 for heuristic turn labels")

    labeled: list[dict[str, Any]] = []
    speaker_index = 0
    previous_end: float | None = None
    for segment in sorted(segments, key=lambda item: (float(item["start"]), float(item["end"]))):
        start = float(segment["start"])
        if previous_end is not None and start - previous_end > pause_threshold:
            speaker_index = (speaker_index + 1) % speakers
        previous_end = float(segment["end"])
        labeled.append(
            {
                **segment,
                "speaker": f"TURN_{speaker_index + 1:02d}",
                "speaker_confidence": "heuristic-low",
            }
        )
    return labeled


def unknown_speaker_labels(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **segment,
            "speaker": "UNKNOWN",
            "speaker_confidence": "none",
        }
        for segment in segments
    ]


def atomic_write_text(path: Path, text: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def build_meeting_minutes_template(metadata: dict[str, Any]) -> str:
    source = metadata.get("source", {})
    return "\n".join(
        [
            "# Meeting Minutes Draft",
            "",
            "## 1. Analysis Note",
            "",
            f"- Source: {source.get('filename', 'unknown')} ({source.get('sha256_prefix', 'no-hash')})",
            f"- Duration: {metadata.get('media', {}).get('duration_seconds', 'unknown')}",
            f"- Format: {metadata.get('media', {}).get('data_format', 'unknown')}",
            f"- Transcription: {metadata.get('engine', 'unknown')} / {metadata.get('model', 'unknown')}",
            f"- Speaker labeling: {metadata.get('speaker_method', 'unknown')}",
            f"- Limitations: {metadata.get('speaker_confidence_note', '')}",
            "",
            "## 2. Role Map",
            "",
            "| Speaker/Turn | Inferred Role | Evidence Timestamp | Confidence | Notes |",
            "| --- | --- | --- | --- | --- |",
            "| UNKNOWN | 미확인 | 미확인 | low | Fill from transcript evidence only. |",
            "",
            "## 3. Executive Summary",
            "",
            "- 작성 필요: transcript 근거로만 요약.",
            "",
            "## 4. Q&A / Discussion Log",
            "",
            "### Q1. 작성 필요",
            "",
            "- **Time:** 미확인",
            "- **Speaker/Role:** 미확인",
            "- **Question intent:** 미확인 또는 추론임을 명시",
            "- **Field answer:** 미확인",
            "- **Answer logic:** 미확인 또는 추론임을 명시",
            "- **Follow-up evidence:** 미정",
            "",
            "## 5. Decisions and Action Items",
            "",
            "| Item | Owner | Due | Evidence |",
            "| --- | --- | --- | --- |",
            "| 미정 | 미정 | 미정 | 미확인 |",
            "",
            "## 6. Risks and Open Questions",
            "",
            "- 작성 필요",
            "",
            "## 7. Uncertainty Register",
            "",
            "| Time | Issue | Why It Matters | Follow-up |",
            "| --- | --- | --- | --- |",
            "| 미확인 | 미확인 | 미확인 | 미정 |",
            "",
            "## 8. One-Sentence Takeaway",
            "",
            "작성 필요.",
            "",
        ]
    )


def write_outputs(
    out_dir: Path,
    metadata: dict[str, Any],
    segments: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": metadata,
        "segments": segments,
        "turns": turns,
    }
    atomic_write_text(
        out_dir / "transcript_segments.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )

    lines = [
        "# Speaker-Labeled Transcript",
        "",
        f"- Source: `{metadata.get('source', {}).get('filename', 'unknown')}`",
        f"- Source hash: `{metadata.get('source', {}).get('sha256_prefix', 'no-hash')}`",
        f"- Transcription engine: {metadata.get('engine', 'unknown')}",
        f"- Speaker method: {metadata.get('speaker_method', 'unknown')}",
        f"- Speaker confidence note: {metadata.get('speaker_confidence_note', '')}",
    ]
    if metadata.get("speaker_diarization_error"):
        lines.append(f"- Diarization warning: {markdown_cell(metadata['speaker_diarization_error'])}")
    lines.extend(
        [
            "",
            "| Time | Speaker | Confidence | Text |",
            "| --- | --- | --- | --- |",
        ]
    )
    for turn in turns:
        start = format_timestamp(float(turn["start"]))
        end = format_timestamp(float(turn["end"]))
        speaker = markdown_cell(turn.get("speaker", "UNKNOWN"))
        confidence = markdown_cell(turn.get("speaker_confidence", "none"))
        text = markdown_cell(turn.get("text", ""))
        lines.append(f"| {start}-{end} | {speaker} | {confidence} | {text} |")
    atomic_write_text(out_dir / "speaker_transcript.md", "\n".join(lines) + "\n")
    atomic_write_text(out_dir / "meeting_minutes_template.md", build_meeting_minutes_template(metadata))


def run_pipeline(args: argparse.Namespace) -> Path:
    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    validate_options(args.speaker_mode, args.speakers, args.pause_threshold, args.max_turn_duration)

    source_hash = file_sha256(audio_path)
    media_metadata = probe_media(audio_path)
    out_base = Path(args.out_dir).expanduser().resolve()
    out_base.mkdir(parents=True, exist_ok=True)
    out_dir = make_run_dir(out_base, audio_path, source_hash, args.run_id)
    if out_dir.exists() and not args.force:
        raise FileExistsError(f"Output directory already exists: {out_dir}. Use --force to overwrite.")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="audio-meeting-") as temp_dir:
        processing_copy = Path(temp_dir) / f"source{audio_path.suffix}"
        shutil.copyfile(audio_path, processing_copy)
        try:
            os.chmod(processing_copy, 0o600)
        except OSError:
            pass

        retained_media: str | None = None
        if args.keep_source_copy:
            retained = out_dir / f"source{audio_path.suffix}"
            shutil.copyfile(audio_path, retained)
            try:
                os.chmod(retained, 0o600)
            except OSError:
                pass
            retained_media = retained.name

        language = None if args.language == "auto" else args.language
        segments, metadata = transcribe_with_faster_whisper(
            processing_copy,
            language,
            args.model,
            args.device,
            args.compute_type,
            args.initial_prompt,
            args.vad_min_silence_ms,
        )

        speaker_method = "none"
        confidence_note = "No acoustic diarization was run; speaker labels are unknown."
        diarization_error: str | None = None
        labeled_segments: list[dict[str, Any]]
        if args.speaker_mode in {"auto", "pyannote"}:
            try:
                speaker_turns = diarize_with_pyannote(processing_copy, args.hf_token, args.speakers)
            except Exception as exc:
                if args.speaker_mode == "pyannote":
                    raise
                diarization_error = f"{type(exc).__name__}: {exc}"
                print(f"Warning: diarization failed; falling back to UNKNOWN speakers: {diarization_error}", file=sys.stderr)
                speaker_turns = []
            if speaker_turns:
                labeled_segments = assign_speakers(segments, speaker_turns)
                speaker_method = "pyannote.audio"
                confidence_note = "Speaker labels are based on acoustic diarization overlap; low-confidence rows remain marked."
            else:
                labeled_segments = unknown_speaker_labels(segments)
                if diarization_error:
                    confidence_note = "Acoustic diarization was attempted but failed; speaker labels are unknown."
        elif args.speaker_mode == "heuristic":
            labeled_segments = apply_heuristic_turn_labels(segments, args.speakers, args.pause_threshold)
            speaker_method = "heuristic-turns"
            confidence_note = (
                "TURN labels are low-confidence pause-based labels, not speaker identity or role."
            )
        else:
            labeled_segments = unknown_speaker_labels(segments)

        turns = group_turns(
            labeled_segments,
            pause_threshold=args.pause_threshold,
            max_turn_duration=args.max_turn_duration,
        )
        metadata.update(
            {
                "schema_version": 2,
                "source": {
                    **source_identifier(audio_path, source_hash),
                    "retained_media": bool(retained_media),
                    "retained_media_filename": retained_media,
                },
                "media": media_metadata,
                "speaker_method": speaker_method,
                "speaker_confidence_note": confidence_note,
                "speaker_diarization_error": diarization_error,
                "pause_threshold": args.pause_threshold,
                "max_turn_duration": args.max_turn_duration,
                "invocation": {
                    "language": args.language,
                    "speaker_mode": args.speaker_mode,
                    "speakers": args.speakers,
                    "keep_source_copy": args.keep_source_copy,
                },
            }
        )
        write_outputs(out_dir, metadata, labeled_segments, turns)
    return out_dir


def run_self_test() -> None:
    transcript = [
        {"start": 0.0, "end": 2.0, "text": "first"},
        {"start": 2.1, "end": 4.0, "text": "second"},
        {"start": 4.1, "end": 5.0, "text": "third"},
    ]
    speaker_turns = [
        {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_01"},
        {"start": 2.5, "end": 4.2, "speaker": "SPEAKER_02"},
    ]
    assigned = assign_speakers(transcript, speaker_turns)
    assert assigned[0]["speaker"] == "SPEAKER_01"
    assert assigned[1]["speaker"] == "SPEAKER_02"
    assert assigned[2]["speaker_confidence"] == "low-coverage"

    turns = group_turns(
        [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "hello"},
            {"start": 1.3, "end": 2.0, "speaker": "SPEAKER_01", "text": "again"},
            {"start": 4.0, "end": 5.0, "speaker": "SPEAKER_02", "text": "answer"},
        ],
        pause_threshold=1.0,
    )
    assert len(turns) == 2
    assert turns[0]["text"] == "hello again"
    validate_options("heuristic", 2, 1.0, 45.0)
    print("PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="?", help="Audio file to transcribe")
    parser.add_argument("--out-dir", default="work/audio-meeting-minutes", help="Output directory")
    parser.add_argument("--language", default="auto", help="Whisper language code or auto")
    parser.add_argument("--model", default="medium", help="faster-whisper model name")
    parser.add_argument("--device", default="cpu", help="faster-whisper device")
    parser.add_argument("--compute-type", default="int8", help="faster-whisper compute type")
    parser.add_argument("--initial-prompt", default=None, help="Optional domain glossary/prompt for Whisper")
    parser.add_argument("--vad-min-silence-ms", type=int, default=350, help="VAD minimum silence in milliseconds")
    parser.add_argument(
        "--speaker-mode",
        choices=["auto", "pyannote", "heuristic", "none"],
        default="auto",
        help="Speaker diarization mode",
    )
    parser.add_argument("--speakers", type=int, default=0, help="Known speaker count when available")
    parser.add_argument("--hf-token", default=None, help="Hugging Face token for pyannote.audio; prefer HF_TOKEN env var")
    parser.add_argument("--pause-threshold", type=float, default=1.2, help="Seconds for turn grouping")
    parser.add_argument("--max-turn-duration", type=float, default=45.0, help="Maximum seconds per output turn")
    parser.add_argument("--run-id", default=None, help="Optional deterministic run directory suffix")
    parser.add_argument("--force", action="store_true", help="Allow reusing an existing run directory")
    parser.add_argument("--keep-source-copy", action="store_true", help="Retain a private source media copy in the run directory")
    parser.add_argument("--self-test", action="store_true", help="Run built-in utility tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0
    if not args.audio:
        parser.error("audio is required unless --self-test is used")
    try:
        out_dir = run_pipeline(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
