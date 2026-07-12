# audio-meeting-minutes 스킬 비판 리뷰 종합 및 개선 내역

## 리뷰 운영

- 방식: 5개 독립 비판 에이전트 병렬 리뷰
- 대상: `skills/audio-meeting-minutes/`
- 원칙: 각 에이전트가 전체 스킬 폴더를 모두 검토하되, 관점만 다르게 부여

## 에이전트 관점

1. Skill discovery / agent usability
2. Audio transcription / diarization engineering
3. Meeting-analysis quality / Korean research-review output
4. Robustness / privacy / security / failure modes
5. Testing / maintainability / CLI/API design

## 반복 지적된 핵심 문제

### 1. 화자 라벨이 실제보다 확정적으로 보임

- 기존 구현은 ASR segment와 diarization turn의 최대 겹침 하나만 보고 전체 발화의 화자를 정했습니다.
- 낮은 overlap과 confidence가 Markdown transcript에 드러나지 않았습니다.
- heuristic mode가 `SPEAKER_XX`처럼 보이면 실제 화자 identity처럼 오해될 수 있었습니다.

**수정:** speaker별 overlap 합산, coverage/dominance 기준 도입, 낮은 coverage는 `UNKNOWN`, 혼합은 `MIXED`, heuristic은 `TURN_XX`로 변경했습니다. Markdown에 confidence 컬럼을 추가했습니다.

### 2. 프라이버시와 덮어쓰기 위험

- 원본 미디어가 결과 폴더에 항상 복사되고, 전체 로컬 경로가 JSON/Markdown에 노출됐습니다.
- 같은 output directory 재사용 시 결과가 덮어써질 수 있었습니다.

**수정:** 기본은 임시 처리 복사본만 사용하고 원본 미디어를 보존하지 않도록 바꿨습니다. `--keep-source-copy`를 명시해야 보존합니다. 출력은 hash/timestamp 기반 run directory에 저장하고, 공유 산출물에는 filename/hash prefix만 기록합니다.

### 3. 산출물 계약과 스크립트 출력 불일치

- output contract는 duration/format, summary/Q&A, role map을 요구했지만 스크립트는 transcript만 생성했습니다.

**수정:** `probe_media()`로 duration/data format/bitrate/size metadata를 기록하고, `meeting_minutes_template.md`를 추가 생성합니다. Role Map과 Uncertainty Register를 contract와 template에 추가했습니다.

### 4. diarization 실패가 조용히 사라짐

- `auto` mode에서 pyannote 실패 원인이 metadata나 transcript에 남지 않았습니다.

**수정:** auto fallback 시 stderr warning과 `speaker_diarization_error` metadata를 남기고, Markdown에도 warning을 표시하도록 했습니다. 명시적 `--speaker-mode pyannote`는 실패를 숨기지 않습니다.

### 5. 일반 오디오를 약속하지만 기본값은 한국어

- skill description은 범용 audio/video를 말하지만 script 기본값은 `ko`였습니다.

**수정:** script 기본 언어를 `auto`로 변경하고, 한국어 회의는 `--language ko` 옵션과 domain prompt를 쓰도록 문서화했습니다.

## 수정된 파일

- `skills/audio-meeting-minutes/SKILL.md`
- `skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py`
- `skills/audio-meeting-minutes/references/output_contract.md`
- `skills/audio-meeting-minutes/agents/openai.yaml`
- `tests/test_audio_meeting_utils.py`

## 검증

- `python tests/test_audio_meeting_utils.py` → PASS
- `python skills/audio-meeting-minutes/scripts/transcribe_meeting_audio.py --self-test` → PASS
- `python "$VALIDATOR" skills/audio-meeting-minutes` → `Skill is valid!`
- 실제 4분 음성 smoke run → transcript JSON, speaker transcript, meeting minutes template 생성 확인
- smoke run 확인: 원본 미디어 기본 미보존, Markdown 전체 로컬 경로 미노출

## 남은 개선 후보

- pyannote 모델 버전 pinning과 local-only model cache 정책
- 긴 회의용 chunking/checkpoint/resume
- word timestamp 기반 diarization boundary split
- 정식 pytest suite를 스킬 폴더 또는 별도 테스트 자산으로 편입
- 자동 Q&A 추출 보조 스크립트 추가
