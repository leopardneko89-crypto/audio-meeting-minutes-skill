# Audio Meeting Minutes Skill

Codex skill for turning meeting audio/video recordings into cautious speaker-labeled transcripts and grounded meeting summaries.

이 스킬은 회의 녹음 파일을 받아 다음 산출물을 만들도록 Codex를 안내합니다.

- 전사 원문
- 화자/턴 라벨이 포함된 대화록
- 회의 요약
- 연구과제 심사·컨설팅 Q&A 정리
- Role Map, Action Items, Uncertainty Register

## Key Principles

- **프라이버시 우선:** 원본 미디어 파일은 기본적으로 결과 폴더에 보존하지 않습니다.
- **화자 구분 신중 처리:** 진짜 diarization이 없으면 `UNKNOWN` 또는 낮은 신뢰도의 `TURN_XX`로 표시합니다.
- **근거 기반 요약:** 질문 의도, 답변 논리, 역할 추정은 transcript timestamp 근거가 있을 때만 작성합니다.
- **로컬 처리 우선:** 기본 전사 경로는 로컬 Python 도구를 사용합니다. 외부 모델 다운로드가 필요한 경우 README와 skill 본문에 명시합니다.

## Install

Clone this repository and copy the skill folder into your Codex skills directory:

```bash
git clone https://github.com/leopardneko89-crypto/audio-meeting-minutes-skill.git
mkdir -p ~/.codex/skills
cp -R audio-meeting-minutes-skill/audio-meeting-minutes ~/.codex/skills/
```

Validate the skill:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py ~/.codex/skills/audio-meeting-minutes
```

## Basic Use

In Codex, upload or reference an audio/video file and ask:

```text
Use $audio-meeting-minutes to transcribe this audio, cautiously label speakers, and summarize the meeting.
```

For Korean research-review meetings:

```text
Use $audio-meeting-minutes to transcribe this Korean review recording and summarize the judges' questions, field answers, risks, and follow-up evidence.
```

## Optional Local Transcription Setup

The skill includes a helper script:

```bash
python3 ~/.codex/skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py /path/to/recording.m4a
```

For local Whisper transcription:

```bash
python3 -m venv work/audio-meeting-venv
work/audio-meeting-venv/bin/python -m pip install --upgrade pip wheel
work/audio-meeting-venv/bin/python -m pip install faster-whisper
work/audio-meeting-venv/bin/python ~/.codex/skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py \
  /path/to/recording.m4a \
  --language auto \
  --speaker-mode auto
```

For Korean audio with domain terms:

```bash
work/audio-meeting-venv/bin/python ~/.codex/skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py \
  /path/to/recording.m4a \
  --language ko \
  --initial-prompt "철도 연구과제 심사, 레일, 분진, 매니퓰레이터, 트랙마스터"
```

## Optional True Diarization

True acoustic speaker diarization requires `pyannote.audio`, a Hugging Face token, and model access.

Use an environment variable rather than passing tokens on the command line:

```bash
work/audio-meeting-venv/bin/python -m pip install pyannote.audio
HF_TOKEN=... work/audio-meeting-venv/bin/python ~/.codex/skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py \
  /path/to/recording.m4a \
  --speaker-mode pyannote \
  --speakers 3
```

If diarization is unavailable, the skill should not invent speaker identity. It should use `UNKNOWN` or explicitly low-confidence `TURN_XX` labels.

## Generated Files

The helper script writes a unique run directory under `work/audio-meeting-minutes` by default:

- `speaker_transcript.md`
- `transcript_segments.json`
- `meeting_minutes_template.md`

The script records source filename and hash prefix, not full local paths, in shareable artifacts.

## Repository Layout

```text
audio-meeting-minutes-skill/
├── audio-meeting-minutes/        # Codex skill folder to copy into ~/.codex/skills
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/output_contract.md
│   └── scripts/transcribe_meeting_audio.py
├── tests/test_audio_meeting_utils.py
├── docs/review-synthesis.md
└── README.md
```

## Test

The tests cover speaker assignment, confidence propagation, heuristic label safety, path redaction, and Markdown escaping. They do not download transcription models.

```bash
python3 tests/test_audio_meeting_utils.py
python3 audio-meeting-minutes/scripts/transcribe_meeting_audio.py --self-test
```

## Privacy Notes

- The script uses a temporary processing copy by default.
- Use `--keep-source-copy` only when you explicitly want to retain the source media in the run directory.
- Shared Markdown/JSON outputs avoid full local path disclosure.
- `faster-whisper` and `pyannote.audio` may download model artifacts into local model caches.

## License

MIT
