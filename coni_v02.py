import speech_recognition as sr
import subprocess
import time
from pathlib import Path
import os
import tempfile


MODEL_DIR = Path("models/en_ryan")
MODEL = MODEL_DIR / "en_US-ryan-high.onnx"
CONFIG = MODEL_DIR / "en_US-ryan-high.onnx.json"
OUT_WAV = "tts_out.wav"
PRE_SILENCE_MS = 2000

if not MODEL.exists or not CONFIG.exists():
    raise SystemExit("Model files not found!")

speaking = False

def _wait_file_stable(path: str, checks: int = 6, sleep_s: float = 0.03) -> None:
    last = -1
    for _ in range(checks):
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        if size == last and size > 1000:
            return
        last = size
        time.sleep(sleep_s)

def _prepend_silence_wav(wav_path: str, ms: int = 300) -> None:
    import wave
    with wave.open(wav_path, "rb") as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())

    nch, sampwidth, framrate, *_ = params
    if(sampwidth != 2):
        return
    
    silence_frames = int(framrate * (ms / 1000.0))
    silence = b"\x00\x00" * silence_frames * nch

    with wave.open(wav_path, "wb") as w:
        w.setparams(params)
        w.writeframes(silence + frames)

def speak(text: str) -> None:
    global speaking

    text = text.strip()
    if not text:
        return
    
    speaking = True
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        subprocess.run(
            ["piper", "--model", str(MODEL), "--config", str(CONFIG), "--output_file", tmp_path],
            input=text.encode("utf-8"),
            check=True
        )

        _wait_file_stable(tmp_path)
        _prepend_silence_wav(tmp_path, PRE_SILENCE_MS)

        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path],
            check=False
        )
    finally:
        speaking = False
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def listen(language: str = "en-US", timeout: int = 6, phrase_time_limit: int = 8) -> str:
    if speaking:
        return ""
    
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.6)
        print("Listening")
        audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

    try:
        return r.recognize_google(audio, language=language)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return "__REQUEST_ERROR__"
    
def main():
    speak("Hello sir, I am ready, say exit to exit.")

    while True:
        text = listen()
        
        if text == "__REQUEST_ERROR__":
            print("Speech Service Error")
            speak("I cannot reach the speech service right now.")
            time.sleep(0.5)
            continue
        if not text:
            continue
        
        print("You said:", text)
        
        lowered = text.lower()
        if "exit" in lowered or "close" in lowered:
            speak("See you soon sir.")
            break

        speak(f"You said: {text}")

if __name__ == "__main__":
    main()