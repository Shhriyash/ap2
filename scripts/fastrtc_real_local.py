from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Generator, Tuple

import numpy as np
from deepgram import DeepgramClient
from fastrtc import AlgoOptions, ReplyOnPause, Stream
from groq import Groq

DEEPGRAM_TTS_DEFAULT_MODEL = "aura-2-orion-en"
DEEPGRAM_TTS_DEFAULT_ENCODING = "linear16"
DEEPGRAM_TTS_DEFAULT_CONTAINER = "wav"
DEEPGRAM_TTS_DEFAULT_SAMPLE_RATE = "24000"
GROQ_TTS_DEFAULT_MODEL = "canopylabs/orpheus-v1-english"
GROQ_TTS_DEFAULT_VOICE = "orion"
GROQ_TTS_DEFAULT_FORMAT = "wav"


class RealFastRTCVoiceAssistant:
    """
    Local FastRTC voice assistant baseline.
    Pipeline: Mic audio -> VAD chunk -> STT -> LLM hook -> TTS -> playback.
    `get_llm_response` is intentionally designed to be overridden by caller integrations.
    """

    def __init__(self) -> None:
        self.temp_dir = Path(__file__).resolve().parents[1] / ".voice_tmp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        api_key = os.getenv("GROQ_API_KEY2") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GROQ_API_KEY2 (or GROQ_API_KEY) for STT.")
        self.groq_client = Groq(api_key=api_key)

        deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        self.deepgram_client = DeepgramClient(api_key=deepgram_api_key) if deepgram_api_key else None

        self.stt_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
        self.tts_debug = os.getenv("TTS_DEBUG") == "1"

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True
        message = str(exc).lower()
        return any(token in message for token in ["rate limit", "rate_limit", "quota", "insufficient"])

    def _synthesize_deepgram(self, text: str, output_path: Path, *, model: str | None = None) -> Path:
        if self.deepgram_client is None:
            raise RuntimeError("DEEPGRAM_API_KEY not configured.")

        model_name = model or os.getenv("DEEPGRAM_TTS_MODEL", DEEPGRAM_TTS_DEFAULT_MODEL)
        encoding = os.getenv("DEEPGRAM_TTS_ENCODING", DEEPGRAM_TTS_DEFAULT_ENCODING)
        container = os.getenv("DEEPGRAM_TTS_CONTAINER", DEEPGRAM_TTS_DEFAULT_CONTAINER)
        sample_rate = int(os.getenv("DEEPGRAM_TTS_SAMPLE_RATE", DEEPGRAM_TTS_DEFAULT_SAMPLE_RATE))

        if output_path.suffix.lower() != f".{container}":
            output_path = output_path.with_suffix(f".{container}")

        response = self.deepgram_client.speak.v1.audio.generate(
            text=text,
            model=model_name,
            encoding=encoding,
            container=container,
            sample_rate=sample_rate,
        )
        if hasattr(response, "stream"):
            output_path.write_bytes(response.stream.getvalue())
            return output_path

        if hasattr(response, "__iter__"):
            with open(output_path, "wb") as audio_file:
                for chunk in response:
                    if chunk:
                        audio_file.write(chunk)
            return output_path

        raise RuntimeError("Deepgram TTS returned unsupported response type.")

    def _synthesize_groq(
        self,
        text: str,
        output_path: Path,
        *,
        model: str | None = None,
        voice: str | None = None,
        audio_format: str | None = None,
    ) -> Path:
        model_name = model or os.getenv("GROQ_TTS_MODEL", GROQ_TTS_DEFAULT_MODEL)
        voice_name = voice or os.getenv("GROQ_TTS_VOICE", GROQ_TTS_DEFAULT_VOICE)
        response_format = audio_format or os.getenv("GROQ_TTS_FORMAT", GROQ_TTS_DEFAULT_FORMAT)

        if response_format and output_path.suffix.lower() != f".{response_format}":
            output_path = output_path.with_suffix(f".{response_format}")

        response = self.groq_client.audio.speech.create(
            model=model_name,
            voice=voice_name,
            input=text,
            response_format=response_format,
        )
        response.write_to_file(str(output_path))
        return output_path

    def transcribe_audio(self, audio_path: Path) -> str | None:
        try:
            with open(audio_path, "rb") as file:
                transcription = self.groq_client.audio.transcriptions.create(
                    file=(audio_path.name, file.read()),
                    model=self.stt_model,
                    response_format="verbose_json",
                )
            return transcription.text
        except Exception as exc:  # pragma: no cover - depends on runtime services
            print(f"STT error: {exc}")
            return None

    async def get_llm_response(self, text: str) -> str:
        # Designed to be overridden by the caller.
        return f"You said: {text}"

    def text_to_speech(self, text: str) -> Path | None:
        output_path = self.temp_dir / f"tts_{uuid.uuid4().hex[:12]}.wav"
        deepgram_exc: Exception | None = None
        try:
            return self._synthesize_deepgram(text, output_path)
        except Exception as exc:
            deepgram_exc = exc
            if self.tts_debug:
                print(f"TTS debug: Deepgram error: {exc!r}")

        try:
            return self._synthesize_groq(text, output_path)
        except Exception as exc:
            if self.tts_debug:
                print(f"TTS debug: Groq error: {exc!r}")
            if deepgram_exc and self._is_rate_limit_error(deepgram_exc):
                print("TTS error: Deepgram rate-limited and Groq fallback failed.")
            else:
                print("TTS error: Deepgram TTS failed and Groq fallback failed.")
            return None

    def play_audio(self, audio_path: Path) -> bool:
        import threading

        def _play_and_delete(path: Path) -> None:
            try:
                if os.name == "nt":
                    played = False
                    if path.suffix.lower() == ".wav":
                        try:
                            import winsound
                            winsound.PlaySound(str(path), winsound.SND_FILENAME)
                            played = True
                        except Exception as exc:
                            print(f"winsound error: {exc}, trying PowerShell fallback...")
                    if not played:
                        import subprocess
                        subprocess.run(
                            ["powershell", "-NoProfile", "-c",
                             f'(New-Object Media.SoundPlayer "{str(path)}").PlaySync()'],
                            check=False,
                            capture_output=True,
                        )
                else:
                    from pydub import AudioSegment
                    from pydub.playback import play
                    audio = AudioSegment.from_file(str(path))
                    play(audio)
            except Exception as exc:  # pragma: no cover
                print(f"Playback error: {exc}")
            finally:
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass

        try:
            t = threading.Thread(target=_play_and_delete, args=(audio_path,), daemon=True)
            t.start()
            return True
        except Exception as exc:  # pragma: no cover
            print(f"Playback launch error: {exc}")
            return False

    def response(self, audio: Tuple[int, np.ndarray]) -> Generator[Tuple[int, np.ndarray], None, None]:
        sample_rate, audio_array = audio
        try:
            if len(audio_array) < 1000:
                return

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = Path(tmp.name)

            import scipy.io.wavfile as wavfile

            valid_sample_rate = max(8000, min(sample_rate, 48000))
            audio_data = np.array(audio_array, dtype=np.int16)
            wavfile.write(temp_path, valid_sample_rate, audio_data)

            transcription = self.transcribe_audio(temp_path)
            temp_path.unlink(missing_ok=True)

            if not transcription or not transcription.strip():
                return

            print(f"user> {transcription}")
            response_text = asyncio.run(self.get_llm_response(transcription))
            if not response_text:
                return

            print(f"agent> {response_text}")
            speech_file = self.text_to_speech(response_text)
            if speech_file and speech_file.exists():
                self.play_audio(speech_file)
        except Exception as exc:  # pragma: no cover - runtime defensive logging
            print(f"FastRTC processing error: {exc}")

    def create_stream(self) -> Stream:
        return Stream(
            modality="audio",
            mode="send-receive",
            handler=ReplyOnPause(
                self.response,
                algo_options=AlgoOptions(
                    speech_threshold=0.2,
                ),
            ),
        )

    def run_console_mode_with_fastrtc_vad(self) -> bool:
        """
        Console recorder loop compatible with the existing reference behavior.
        Uses manual key control, then routes captured chunks through `response`.
        """
        import pyaudio

        print("FastRTC Voice Assistant - Console Mode")
        print("Manual audio recording with FastRTC VAD processing")

        chunk = 1024
        sample_format = pyaudio.paInt16
        channels = 1
        sample_rate = 16000

        pa = pyaudio.PyAudio()

        print("Choose recording mode:")
        print("1. Hold SPACE to record (release to stop)")
        print("2. Press SPACE to start, auto-stop when you finish speaking")
        print("Press Q to quit")
        mode_choice = input("Enter mode (1 or 2): ").strip()

        try:
            import keyboard

            while True:
                print("\nWaiting for SPACE key...")
                keyboard.wait("space")
                if keyboard.is_pressed("q"):
                    break

                frames: list[bytes] = []
                stream = pa.open(
                    format=sample_format,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    frames_per_buffer=chunk,
                )
                recording_start = time.time()

                if mode_choice == "1":
                    print("Recording... (release SPACE to stop)")
                    while keyboard.is_pressed("space"):
                        frames.append(stream.read(chunk))
                        if time.time() - recording_start > 20:
                            print("Max recording window reached.")
                            break
                else:
                    print("Recording... (auto-stop on silence)")
                    silence_threshold = 500
                    silence_chunks = 30
                    silent_count = 0
                    has_spoken = False
                    while True:
                        data = stream.read(chunk)
                        frames.append(data)

                        audio_chunk = np.frombuffer(data, dtype=np.int16)
                        rms = np.sqrt(np.maximum(0, np.mean(audio_chunk.astype(np.float32) ** 2)))
                        if rms > silence_threshold:
                            has_spoken = True
                            silent_count = 0
                        elif has_spoken:
                            silent_count += 1

                        if has_spoken and silent_count > silence_chunks:
                            print("Silence detected, stopping.")
                            break
                        if time.time() - recording_start > 20:
                            print("Max recording window reached.")
                            break

                stream.stop_stream()
                stream.close()

                if frames:
                    audio_data = b"".join(frames)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    result = self.response((sample_rate, audio_array))
                    if result:
                        for _ in result:
                            pass
        except ImportError:
            print("`keyboard` package unavailable. Falling back to Enter-to-record mode.")
            while True:
                cmd = input("\nPress Enter to record (or type quit): ").strip().lower()
                if cmd == "quit":
                    break
                frames: list[bytes] = []
                stream = pa.open(
                    format=sample_format,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    frames_per_buffer=chunk,
                )
                for _ in range(0, int(sample_rate / chunk * 3)):
                    frames.append(stream.read(chunk))
                stream.stop_stream()
                stream.close()
                audio_data = b"".join(frames)
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                result = self.response((sample_rate, audio_array))
                if result:
                    for _ in result:
                        pass
        finally:
            try:
                pa.terminate()
            except Exception:
                pass

        return True

    def cleanup(self) -> None:
        try:
            for file in self.temp_dir.glob("*"):
                try:
                    file.unlink()
                except Exception:
                    pass
        except Exception:
            pass
