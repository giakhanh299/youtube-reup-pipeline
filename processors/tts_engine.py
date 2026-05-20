from __future__ import annotations
from pathlib import Path
import os
import subprocess
import tempfile


def setup_google_credentials(key_dir: str) -> None:
    key_path = Path(key_dir)
    if not key_path.exists():
        raise FileNotFoundError(f"Không thấy thư mục key Google: {key_dir}")
    json_files = list(key_path.glob('*.json'))
    if not json_files:
        raise FileNotFoundError(f"Không thấy file .json Google key trong: {key_dir}")
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(json_files[0])


def google_tts(text: str, output_file: Path, voice_cfg: dict) -> None:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    gender_name = voice_cfg.get('gender', 'FEMALE').upper()
    gender = getattr(texttospeech.SsmlVoiceGender, gender_name, texttospeech.SsmlVoiceGender.FEMALE)

    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code=voice_cfg.get('language_code', 'vi-VN'),
            name=voice_cfg.get('name', 'vi-VN-Wavenet-A'),
            ssml_gender=gender,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=float(voice_cfg.get('speaking_rate', 1.0)),
        ),
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(response.audio_content)


def local_command_tts(text: str, output_file: Path, voice_cfg: dict) -> None:
    """Chỗ nối cho F5-TTS / XTTS / GPT-SoVITS local sau này."""
    command_template = voice_cfg['command']
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.txt', delete=False) as f:
        f.write(text)
        text_file = f.name
    try:
        cmd = command_template.format(text_file=text_file, output_file=str(output_file))
        subprocess.run(cmd, shell=True, check=True)
    finally:
        try:
            os.remove(text_file)
        except OSError:
            pass


def create_voice(text: str, output_file: Path, voice_cfg: dict, google_key_dir: str) -> None:
    engine = voice_cfg.get('tts_engine') or voice_cfg.get('engine', 'google')
    if engine == 'google':
        setup_google_credentials(google_key_dir)
        google_tts(text, output_file, voice_cfg)
    elif engine == 'local_command':
        local_command_tts(text, output_file, voice_cfg)
    else:
        raise ValueError(f"Chưa hỗ trợ TTS engine: {engine}")
