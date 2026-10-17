# Validation records

Each round keeps a single summary file. The raw intermediate runs were removed to
keep the repository small; they are still recoverable from git history:

```bash
git log --diff-filter=D --summary -- validation/
```

| Round | File | What it measured |
|---|---|---|
| `plain-language-2026-10-16` | `summary.json` | Plain-language answers before/after the grounding and example fixes (final-with-filter run) |
| `expert-meeting-2026-10-16` | `summary.json` | Vietnamese expert-role answers on the FPTEELiterature snapshot, concurrent sessions |
| `professional-2026-10-17` | `summary.json` | Whisper WER on 12 Google FLEURS Vietnamese clips (base / small / medium, plus 15 dB noise) |
| `real-interview-2026-10-16` | `summary.json` | Replay of recorded interview audio through the live pipeline |
| `server-2026-10-16` | `summary.json` | End-to-end WebSocket/runtime smoke on a private environment |
| `audit-2026-10-17` | `summary.md` | 34-case adversarial + synthesized-voice audit (`scripts/voice_audit.py`) |

These are engineering measurements on small fixtures and specific hardware. They
are not accuracy guarantees for meetings, room audio or realtime operation.
