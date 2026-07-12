# Audio Meeting Output Contract

Use this structure for meeting/review recordings unless the user asks for a different format. For Korean research-review recordings, keep section labels in Korean where useful.

## 1. Analysis Note

- Source filename or redacted source identifier; do not expose full local paths in shareable outputs
- Duration and format
- Transcription engine/model
- Speaker labeling method: `pyannote.audio`, `heuristic-turns`, or `none`
- Confidence note and known limitations

## 2. Speaker-Labeled Transcript

Use a table:

| Time | Speaker | Text |
| --- | --- | --- |
| 00:00-00:12 | SPEAKER_01 | ... |

Rules:

- Use `SPEAKER_01`, `SPEAKER_02`, etc. only for true diarization.
- Use `TURN_01`, `TURN_02`, etc. only for explicitly low-confidence heuristic turn labels.
- Use `UNKNOWN` when the speaker cannot be separated.
- Show confidence for each row or turn when available.
- Add `(불명확)` for important terms that the audio or model could not resolve.

## 3. Executive Summary

Write 3-7 bullets covering:

- Meeting purpose
- Most important conclusions
- Main disagreements or concerns
- Follow-up work

## 4. Q&A / Discussion Log

For each major exchange:

### Q1. [Question or comment]

- **Time:** `MM:SS-MM:SS`
- **Speaker/Role:** 심사위원, 발표자, 컨설턴트, or unknown
- **Question intent:** What concern the question tests
- **Field answer:** What was answered on site
- **Answer logic:** Why the answer is persuasive or weak
- **Follow-up evidence:** Data, slides, estimates, or experiments needed

Rules:

- Mark `Question intent` and `Answer logic` as inference unless directly stated.
- Write `미확인` when the transcript does not support a field.
- Do not infer 심사위원/발표자/컨설턴트 roles from `SPEAKER_XX` or `TURN_XX` alone.

## 4A. Role Map

| Speaker/Turn | Inferred Role | Evidence Timestamp | Confidence | Notes |
| --- | --- | --- | --- | --- |

Use `미확인` by default. Require transcript evidence for every role assignment.

## 5. Decisions and Action Items

Use a table:

| Item | Owner | Due | Evidence |
| --- | --- | --- | --- |

If owner or due date is not spoken, write `미정`.

## 6. Risks and Open Questions

List:

- Technical risks
- Budget/commercialization risks
- Stakeholder concerns
- Transcript uncertainty that could change the interpretation

## 6A. Uncertainty Register

| Time | Issue | Why It Matters | Follow-up |
| --- | --- | --- | --- |

Include low-confidence speaker labels, unclear domain terms, suspected transcription errors, and summary-critical gaps.

## 7. One-Sentence Takeaway

End with one concise sentence that captures the practical meaning of the meeting.
