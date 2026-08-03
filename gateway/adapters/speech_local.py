"""Local speech: hearing and speaking, with nothing leaving the machine.

Hearing is whisper.cpp. Speaking is Piper. Both run on the machine, both
run offline, and both are the deployed path rather than a stand-in for it,
which is why they are used on the bench too.

These are the only files that name either of them.

Licensing, checked before integration as the licensing law requires:
whisper.cpp is MIT and its weights are MIT from OpenAI; Piper's engine is
MIT. The voice is the part that catches people out, because a Piper voice
carries its own licence and most of the well-known English ones are
research-only or non-commercial. The voice here is LibriTTS-R, CC BY 4.0,
built from public-domain LibriVox recordings. See LICENSES.md.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from gateway.adapters.base import register_adapter
from gateway.capabilities import (
    Capability,
    GatewayError,
    Speech,
    SpeechRequest,
    Transcription,
    TranscriptionRequest,
)

log = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("ARGUS_MODEL_DIR", "var/models"))
WHISPER_MODEL = MODEL_DIR / "ggml-base.en.bin"
PIPER_VOICE = MODEL_DIR / "en_US-libritts_r-medium.onnx"

# Whisper wants 16 kHz mono. Anything else gets converted rather than
# refused: a browser sends what its codec produces and should not have to
# know what a recogniser prefers.
WHISPER_RATE = 16_000


class WhisperLocal:
    """Hearing, on the machine."""

    name = "whisper_local"

    def __init__(self, model_path: Path | str = WHISPER_MODEL, binary: str = "whisper-cli"):
        self._model = Path(model_path)
        self._binary = binary

    def capabilities(self) -> set[Capability]:
        return {Capability.TRANSCRIBE}

    @property
    def leaves_the_machine(self) -> bool:
        return False

    def available(self) -> tuple[bool, str]:
        if shutil.which(self._binary) is None:
            return False, f"{self._binary} is not installed"
        if not self._model.exists():
            return False, f"the speech model is missing from {self._model}"
        return True, "ready"

    def transcribe(self, request: TranscriptionRequest) -> Transcription:
        ok, why = self.available()
        if not ok:
            raise GatewayError(f"cannot hear: {why}")

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / f"in.{request.audio_format}"
            source.write_bytes(request.audio)
            wav = self._to_wav(source, Path(tmp) / "in16k.wav")

            try:
                result = subprocess.run(
                    [self._binary, "-m", str(self._model), "-f", str(wav), "-nt", "--no-prints"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                # Every failure leaves as a GatewayError so the voice
                # service can answer in words. An escaped subprocess
                # exception becomes a 500 and reaches the operator as
                # "Internal Server Error", which is both useless and a
                # system term at the waterline.
                raise GatewayError(f"the recogniser failed: {exc}") from exc
        if result.returncode != 0:
            raise GatewayError(f"the recogniser failed: {result.stderr.strip()[:200]}")

        text = " ".join(result.stdout.split()).strip()
        # whisper.cpp marks non-speech with bracketed tags. An operator who
        # said nothing should produce an empty transcript, not the word
        # "BLANK_AUDIO", which downstream would treat as an order.
        for tag in ("[BLANK_AUDIO]", "(blank audio)", "[SILENCE]"):
            text = text.replace(tag, "").strip()

        # No confidence is reported rather than a number invented. The
        # honesty law makes "we do not know" a legitimate answer and a
        # fabricated 1.0 an illegitimate one.
        return Transcription(text=text, confidence=None)

    def _to_wav(self, source: Path, target: Path) -> Path:
        if shutil.which("ffmpeg") is None:
            if source.suffix == ".wav":
                return source
            raise GatewayError("ffmpeg is not installed, so only wav audio can be heard")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-ar", str(WHISPER_RATE), "-ac", "1", str(target)],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise GatewayError(f"could not read that audio: {exc}") from exc
        return target


class PiperLocal:
    """Speaking, on the machine."""

    name = "piper_local"

    def __init__(self, voice_path: Path | str = PIPER_VOICE, speaker: int = 0):
        self._voice = Path(voice_path)
        self._speaker = speaker

    def capabilities(self) -> set[Capability]:
        return {Capability.SPEAK}

    @property
    def leaves_the_machine(self) -> bool:
        return False

    def available(self) -> tuple[bool, str]:
        if not self._voice.exists():
            return False, f"the voice is missing from {self._voice}"
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "the speech synthesiser is not installed"
        return True, "ready"

    def speak(self, request: SpeechRequest) -> Speech:
        ok, why = self.available()
        if not ok:
            raise GatewayError(f"cannot speak: {why}")

        import sys

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.wav"
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "piper",
                        "-m",
                        str(self._voice),
                        "-s",
                        str(self._speaker),
                        "-f",
                        str(out),
                    ],
                    input=request.text,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                raise GatewayError(f"the synthesiser failed: {exc}") from exc
            if result.returncode != 0 or not out.exists():
                raise GatewayError(f"the synthesiser failed: {result.stderr.strip()[:200]}")
            audio = out.read_bytes()

        # The text goes back with the audio, always. The honesty law
        # requires that everything spoken is also printed, and returning
        # them together makes printing nothing the awkward path.
        return Speech(audio=audio, audio_format="wav", text=request.text)


def wav_duration_s(audio: bytes) -> float:
    """How long a clip is. Used to keep replies inside a sane length."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(audio)
        handle.flush()
        with wave.open(handle.name) as clip:
            return clip.getnframes() / float(clip.getframerate())


register_adapter("whisper_local", WhisperLocal)
register_adapter("piper_local", PiperLocal)
