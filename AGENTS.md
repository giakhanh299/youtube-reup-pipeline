# AGENTS.md

This repo is a multi-channel YouTube reup pipeline.

Rules for Codex:
- Google Sheet is the single source of truth.
- Do not hardcode channel, voice, music, logo, overlay, or folder paths.
- Keep Windows compatibility.
- Keep old behavior working.
- Input files may be:
  - video.mp4 + video.srt
  - video.mp4 + video_vi.srt
  - video.mp4 + video.txt
- Output must be per-channel processed video.
- Do not implement YouTube upload yet.
- Use modular processors.
- Add logging and config validation.
- Make small safe changes.