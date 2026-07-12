---
name: audio-meeting-minutes
description: Use when a user uploads or references audio/video recordings and asks for transcription, cautious speaker labeling, diarization, meeting minutes, Q&A extraction, or Korean research-review discussion summaries.
---

# Audio Meeting Minutes

## Core Rule

Turn the recording into two deliverables: a transcript with cautious speaker/turn labels and a meeting summary grounded in that transcript. Preserve uncertainty: never present heuristic turn labels as true acoustic speaker diarization or role identity.

## Workflow

1. Copy temporary source audio/video into a workspace `work/` processing location before slow model loading. Do not keep a durable source-media copy unless the user asks or `--keep-source-copy` is used.
2. Inspect duration and format with available local tools (`afinfo`, `ffprobe`, or equivalent), or rely on the script metadata when it can probe the media.
3. Run transcription with `scripts/transcribe_meeting_audio.py` when Python audio tooling is available.
4. If multiple speakers are likely, prefer true diarization with `pyannote.audio` and `HF_TOKEN`/`HUGGINGFACE_TOKEN`. If unavailable, use `UNKNOWN`; use `--speaker-mode heuristic --speakers N` only for low-confidence `TURN_XX` labels, not identity.
5. Review the transcript for obvious domain-term errors before summarizing. Correct only when context makes the correction defensible.
6. Read `references/output_contract.md` before drafting the final deliverable.
7. Move or rewrite the filled final meeting minutes under the workspace `outputs/` directory when file output is useful. Keep raw transcript runs in `work/` unless the user wants a durable artifact.

## Script Usage

Resolve the directory containing this `SKILL.md`, then resolve the script and reference
files relative to that directory. Do not assume a home directory or checkout location.
Pass every resolved path as one quoted argument so spaces and non-ASCII characters remain
intact:

```bash
python "<skill-root>/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a" \
  --out-dir work/audio-meeting-minutes \
  --language auto \
  --model medium \
  --speaker-mode auto
```

If `faster-whisper` is missing, install it in an isolated workspace venv:

```bash
python -m venv work/audio-meeting-venv
# Activate the venv with the current shell's standard command, then:
python -m pip install --upgrade pip wheel
python -m pip install faster-whisper
python "<skill-root>/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a"
```

For Korean meetings, pass `--language ko` and optionally `--initial-prompt "철도 연구과제 심사, 레일, 분진, 매니퓰레이터"` when domain terms matter.

For true diarization, use `pyannote.audio` only when the environment has a Hugging Face token and model access. Prefer environment variables over `--hf-token` because command-line tokens can leak via shell history or process listings:

```bash
python -m pip install pyannote.audio
python "<skill-root>/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a" \
  --speaker-mode pyannote --speakers 3
```

The script creates a unique run directory and writes `speaker_transcript.md`, `transcript_segments.json`, and `meeting_minutes_template.md`. If true diarization is not available, do not block the task. Produce a transcript with `UNKNOWN` speakers or explicitly low-confidence `TURN_XX` labels, then infer roles only with timestamped text evidence.

## Summary Rules

- For ordinary meetings: include agenda, key points, decisions, action items, owners, dates, risks, and unresolved questions.
- For research review or consulting debriefs: prioritize 심사위원 질문, 질문 의도, 현장 답변, 답변 논리, 보강자료 필요사항.
- Keep transcript-grounding visible by citing timestamps for major questions and decisions.
- Separate facts from inference. Mark uncertain words as `(불명확)` or explain that the audio did not support a confident reading.
- Include a Role Map when using speaker/turn labels: speaker or turn id, inferred role, evidence timestamp, confidence, and notes. Use `미확인` when unsupported.
- Include an Uncertainty Register for low-confidence speaker labels, unclear technical terms, and transcript spans that could change interpretation.
- When the user corrects the file or says a previous file was wrong, discard prior transcript assumptions and analyze only the newly specified file.
