import speech_recognition as sr
import subprocess
import time
from pathlib import Path
import os
import tempfile
import re
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
from zoneinfo import ZoneInfo


load_dotenv()
client = OpenAI()



MODEL_DIR_EN = Path("models/en_ryan")
MODEL_EN = MODEL_DIR_EN / "en_US-ryan-high.onnx"
CONFIG_EN = MODEL_DIR_EN / "en_US-ryan-high.onnx.json"

MODEL_DIR_TR = Path("models/tr")
MODEL_TR = MODEL_DIR_TR / "tr_TR-dfki-medium.onnx"
CONFIG_TR = MODEL_DIR_TR / "tr_TR-dfki-medium.onnx.json"

OUT_WAV = "tts_out.wav"
PRE_SILENCE_MS = 2000

if not MODEL_EN.exists() or not CONFIG_EN.exists():
    raise SystemExit("EN model files not found!")

if not MODEL_TR.exists() or not CONFIG_TR.exists():
    raise SystemExit("TR model dosyaları bulunamadı!")

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

def _pad_silence_wav(wav_path: str, pre_ms: int = 2000, post_ms: int = 400) -> None:
    import wave

    with wave.open(wav_path, "rb") as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())

    nch, sampwidth, framerate, *_ = params
    if(sampwidth != 2):
        return
    
    pre_frames = int(framerate * (pre_ms / 1000.0))
    post_frames = int(framerate * (post_ms / 1000.0))
    
    silence_pre = (b"\x00\x00" * nch) * pre_frames
    silence_post = (b"\x00\x00" * nch) * post_frames

    with wave.open(wav_path, "wb") as w:
        w.setparams(params)
        w.writeframes(silence_pre + frames + silence_post)

def speak(text: str, lang: str = "en") -> None:
    global speaking

    text = (text or "").strip()
    if not text:
        return
    
    speaking = True
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        if lang == "tr":
            model, config = MODEL_TR, CONFIG_TR
        else:
            model, config = MODEL_EN, CONFIG_EN
        
        subprocess.run(
            ["piper", "--model", str(model), "--config", str(config), "--output_file", tmp_path],
            input=text.encode("utf-8"),
            check=True
        )

        _wait_file_stable(tmp_path)
        _pad_silence_wav(tmp_path,
                        pre_ms=2000,
                        post_ms=500
                        )

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

TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
EN_COMMON = {"the", "and", "is", "are", "what", "how", "you", "your", "i", "we", "can", "do", "to", "for", "x", "exit", "ex"}

def _score_test(text: str, lang: str) -> float:
    t = (text or "").strip()
    if not t:
        return -1e9
    
    score = 0.0
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", t)

    if len(words) >= 3:
        score += 1
    if len(t) >= 10:
        score += 0.5
    
    if lang == "tr":
        score += sum(1 for ch in t if ch in TR_CHARS) * 1.2
        score -= sum(1 for w in words if w.lower() in EN_COMMON) * 0.2
    if lang == "en":
        score += sum(1 for w in words if w.lower() in EN_COMMON) * 0.6
        score -= sum(1 for ch in t if ch in TR_CHARS) * 0.8

    return score


def _listen_audio(timeout: int = 6, phrase_time_limit: int = 8) -> str:
    if speaking:
        return None
    
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.2)
        print("Listening")
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return None
    return r, audio

def listen_auto(timeout: int = 6, phrase_time_limit: int = 8) -> tuple[str, str]:
    pair = _listen_audio(timeout=timeout, phrase_time_limit=phrase_time_limit)
    if not pair:
        return "", ""
    
    r, audio = pair

    try:
        en_text = r.recognize_google(audio, language = "en-US")
    except sr.UnknownValueError:
        en_text = ""
    except sr.RequestError:
        return "__REQUEST_ERROR__", ""
    
    try:
        tr_text = r.recognize_google(audio, language = "tr-TR")
    except sr.UnknownValueError:
        tr_text = ""
    except sr.RequestError:
        return "__REQUEST_ERROR__", ""
    
    tr_text = (tr_text or "").strip()
    en_text = (en_text or "").strip()

    if not tr_text and not en_text:
        return "", ""
    
    tr_score = _score_test(tr_text, "tr")
    en_score = _score_test(en_text, "en")

    if tr_score >= en_score:
        return tr_text, "tr"
    return en_text, "en"

def ask_ai(user_text: str, lang: str, history: list[dict]) -> str:

    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    today_str_tr = now.strftime("%d %B %Y")
    today_iso = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    system_tr = (
        "Sen bir sesli asistansın, ismin 'Coni' ve bana efendim diye hitap ediyorsun. Cevapların kısa, net ve konuşma dilinde olsun."
        "Gereksiz teknik detay verme. Maksimum 3-5 cümle. Sonuna 'nasıl yardımcı olabilirim' cümlesini ekleme."
        f"Şu an Türkiye saatine göre tarih: {today_iso}, saat: {time_str}, Europe/Istanbul"
        "Eğer kullanıcı 'bugün' derse bu tarihi baz al"
    )
    system_en = (
        "You are a voice asistant, your name is 'Coni' and you call me sir. Keep answers short, clear and spoken-friendly."
        "Avoid unnecessary technical detail. Max 3-5 sentences. Don't add the 'how can help you' sentence at the end."
        f"Current date/time (Europe/Istanbul): {today_iso}"
        "If the user says 'today' use this data."
    )

    messages = [{"role": "system", "content": system_tr if lang == "tr" else system_en}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=messages
        )
        answer = (resp.output_text or "").strip()
        if not answer:
            return "bir cevap üretemedim" if lang == "tr" else "I couldn't generate an answer"
        return answer
    except Exception as e:
        print("OpenAI error", e)
        return "Şu an yapay zekaya ulaşamıyorum" if lang == "tr" else "I can't reach the ai."
    

    
def main():
    speak("Hello sir, I am ready, say exit to exit.", lang="en")
    history = []


    while True:
        text, lang = listen_auto(timeout=6, phrase_time_limit=10)
        
        if text == "__REQUEST_ERROR__":
            print("Speech Service Error")
            speak("I cannot reach the speech service right now.")
            time.sleep(0.5)
            continue
        if not text:
            continue
        
        if lang == "tr":
            print(f"Şunu dedin ({lang}): {text}")
        else:
            print(f"You said ({lang}): {text}")
        
        lowered = text.lower()
        if "exit" in lowered or "close" in lowered:
            speak("See you soon sir!", lang="en")
            break
        if "çık" in lowered or "kapat" in lowered:
            speak("Görüşürüz efendim!", lang="tr")
            break

        answer = ask_ai(text, lang, history)

        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        history[:] = history[-6:]

        speak(answer, lang=lang)
        print(answer)

        

if __name__ == "__main__":
    main()