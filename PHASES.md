# Reup Pipeline - Development Phases

## Phase 0 - Repo hygiene
- Remove secrets from code.
- Add `.gitignore`.
- Move all paths and IDs to Google Sheet/config only.
- Verify `python pipeline.py --dry-run` works.

## Phase 1 - Google Sheet control center
- CHANNEL_CONFIG controls channels, folders, voice_id, music_pack, overlay_pack, render_preset.
- VOICE_CONFIG controls TTS engine, speaker, speed, pitch, volume, ref audio.
- MUSIC_PACK controls music file, volume, loop, start/end.
- OVERLAY_PACK controls logo, blur background, opacity, x/y, grain/icon.
- RENDER_PRESET controls resolution, encoder, crop, speed random, subtitle style.
- VIDEO_QUEUE controls each job status: NEW, PROCESSING, READY_UPLOAD, UPLOADED, ERROR.

## Phase 2 - Input matching
- Auto match `video.mp4` with `video_vi.srt`, `video.srt`, or `video.txt`.
- Prefer `_vi.srt` if it exists.
- Fallback to txt.
- Write matched text path back to VIDEO_QUEUE.

## Phase 3 - Voice engine
- Keep Google TTS compatible.
- Add local TTS adapter later: XTTS/F5-TTS/GPT-SoVITS.
- Voice must be selected by `voice_id` from Sheet, not hardcoded.
- Cache generated TTS in runtime/cache.

## Phase 4 - Render engine
- Add background blur.
- Add logo watermark by channel.
- Add music pack.
- Add overlay pack.
- Add subtitle style.
- Use NVENC if available.

## Phase 5 - Multi-channel scaling
- One source video can render many variants for many channels.
- Prevent duplicate processing by job_id.
- Add worker lock to avoid two workers processing the same row.

## Phase 6 - Upload handoff
- Export final video to output folder by channel.
- Update VIDEO_QUEUE to READY_UPLOAD.
- Existing upload tool reads READY_UPLOAD jobs.

## Phase 7 - Codex cleanup tasks
- Add tests for text matching and sheet parsing.
- Add CLI commands: dry-run, process-one, process-channel.
- Improve error handling and logs.
