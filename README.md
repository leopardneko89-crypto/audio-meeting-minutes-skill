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

The repository is both a standalone Agent Skill and a Codex plugin package. Its
`.codex-plugin/plugin.json` exposes `skills/audio-meeting-minutes/` without duplicating the skill.
A SHA-pinned Codex marketplace can therefore install the repository as a plugin, while the
portable copy workflow below remains available for other Agent Skills clients.

Clone this repository and copy the skill folder into the current personal skills directory.
On POSIX shells:

```bash
git clone https://github.com/leopardneko89-crypto/audio-meeting-minutes-skill.git
SKILLS_ROOT="$HOME/.agents/skills"
SKILL_SOURCE="audio-meeting-minutes-skill/skills/audio-meeting-minutes"
SKILL_DEST="$SKILLS_ROOT/audio-meeting-minutes"
mkdir -p "$SKILL_DEST"
cp -R "$SKILL_SOURCE/." "$SKILL_DEST/"
```

On PowerShell:

```powershell
git clone https://github.com/leopardneko89-crypto/audio-meeting-minutes-skill.git
$SkillsRoot = Join-Path $HOME ".agents\skills"
$SkillSource = Join-Path (Get-Location) "audio-meeting-minutes-skill\skills\audio-meeting-minutes"
$SkillDest = Join-Path $SkillsRoot "audio-meeting-minutes"
New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
Get-ChildItem -LiteralPath $SkillSource -Force |
  Copy-Item -Destination $SkillDest -Recurse -Force
```

The repository CI runs the pinned official Codex skill and plugin validators. For a local smoke check,
resolve the installed script from `$HOME/.agents/skills/audio-meeting-minutes` (or the
PowerShell equivalent shown above) and run it with `--self-test`.

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

The skill includes a helper script. Quote the resolved skill path so spaces and non-ASCII
characters in the home or checkout path remain intact:

```bash
SKILL_ROOT="$HOME/.agents/skills/audio-meeting-minutes"
python "$SKILL_ROOT/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a"
```

For local Whisper transcription:

```bash
python -m venv work/audio-meeting-venv
# Activate the venv with your shell's standard command, then:
python -m pip install --upgrade pip wheel
python -m pip install faster-whisper
python "$SKILL_ROOT/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a" \
  --language auto \
  --speaker-mode auto
```

For Korean audio with domain terms:

```bash
python "$SKILL_ROOT/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a" \
  --language ko \
  --initial-prompt "철도 연구과제 심사, 레일, 분진, 매니퓰레이터, 트랙마스터"
```

## Optional True Diarization

True acoustic speaker diarization requires `pyannote.audio`, a Hugging Face token, and model access.

Set `HF_TOKEN` through your shell or secret manager rather than passing tokens on the
command line, then run:

```bash
python -m pip install pyannote.audio
python "$SKILL_ROOT/scripts/transcribe_meeting_audio.py" "/path/to/recording.m4a" \
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
├── .codex-plugin/plugin.json
├── skills/
│   └── audio-meeting-minutes/    # Skill folder to copy into $HOME/.agents/skills
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── references/output_contract.md
│       └── scripts/transcribe_meeting_audio.py
├── tests/test_audio_meeting_utils.py
├── docs/review-synthesis.md
└── README.md
```

## Test

The tests cover speaker assignment, confidence propagation, heuristic label safety, path redaction, and Markdown escaping. They do not download transcription models.

```bash
python tests/test_audio_meeting_utils.py
python -m unittest discover -s tests -p "test_package.py" -v
python skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py --self-test
```

## Privacy Notes

- The script uses a temporary processing copy by default.
- Use `--keep-source-copy` only when you explicitly want to retain the source media in the run directory.
- Shared Markdown/JSON outputs avoid full local path disclosure.
- `faster-whisper` and `pyannote.audio` may download model artifacts into local model caches.

## License

MIT
