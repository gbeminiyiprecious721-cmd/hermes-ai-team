"""Jarvis voice service: local neural speech (Kokoro, open source) with a custom voice blend and a light signature treatment.
Listens on 127.0.0.1 only. POST /tts {text, voice} -> audio/mpeg. GET /voices -> presets. GET /health.
Runs in its own virtualenv (/root/jarvis-voice/venv); Hermes itself is not touched."""
import json
import subprocess
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

HERE = "/root/jarvis-voice/"
PORT = 9931
MAX_CHARS = 420

# Each preset is a weighted blend of Kokoro voice styles. "jarvis" is the signature voice: a calm, low British baritone that exists only in this mix.
PRESETS = {
    "jarvis": {"label": "Jarvis (signature blend)", "mix": {"bm_george": 0.55, "bm_fable": 0.30, "bm_lewis": 0.15}, "speed": 0.97, "lang": "en-gb", "depth": 0.965},
    "george": {"label": "George (British, warm)", "mix": {"bm_george": 1.0}, "speed": 1.0, "lang": "en-gb", "depth": 1.0},
    "lewis": {"label": "Lewis (British, crisp)", "mix": {"bm_lewis": 1.0}, "speed": 1.0, "lang": "en-gb", "depth": 1.0},
    "fable": {"label": "Fable (British, storyteller)", "mix": {"bm_fable": 1.0}, "speed": 0.98, "lang": "en-gb", "depth": 0.98},
    "daniel": {"label": "Daniel (British, smooth)", "mix": {"bm_daniel": 1.0}, "speed": 1.0, "lang": "en-gb", "depth": 1.0},
    "onyx": {"label": "Onyx (American, deep)", "mix": {"am_onyx": 0.7, "am_michael": 0.3}, "speed": 0.98, "lang": "en-us", "depth": 0.97},
    "emma": {"label": "Emma (British, female)", "mix": {"bf_emma": 0.7, "bf_isabella": 0.3}, "speed": 1.0, "lang": "en-gb", "depth": 1.0},
}

so = ort.SessionOptions()
so.intra_op_num_threads = 2
so.inter_op_num_threads = 1
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
KOKORO = Kokoro.from_session(ort.InferenceSession(HERE + "kokoro.fp32.onnx", sess_options=so, providers=["CPUExecutionProvider"]), HERE + "voices.bin")
LOCK = threading.Lock()
CACHE = OrderedDict()   # (voice, text) -> mp3 bytes, so repeated phrases ("One moment.") are instant


def style_for(preset):
    total = sum(preset["mix"].values())
    return np.sum([KOKORO.get_voice_style(v) * (w / total) for v, w in preset["mix"].items()], axis=0)


STYLES = {}


def encode(samples, sr, depth):
    """Float samples -> mp3 with the signature treatment: slightly lower (deeper) voice at the same speed, warmth, presence, a faint
    metallic room, gentle compression and a limiter. Kept subtle so it stays clear on a phone speaker."""
    filt = []
    if depth != 1.0:
        filt.append("asetrate=%d,aresample=%d,atempo=%.5f" % (int(sr * depth), sr, 1.0 / depth))
    filt += ["highpass=f=70", "equalizer=f=170:t=q:w=1.0:g=2.2", "equalizer=f=3200:t=q:w=1.2:g=2.6", "aecho=0.88:0.32:11|23:0.20|0.10",
             "acompressor=threshold=-20dB:ratio=3:attack=6:release=90:makeup=3", "alimiter=limit=0.92"]
    pcm = np.clip(samples, -1, 1).astype("<f4").tobytes()
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0", "-af", ",".join(filt),
                        "-ar", "24000", "-codec:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1"], input=pcm, capture_output=True, timeout=30)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("encode failed: " + p.stderr.decode("utf-8", "ignore")[:200])
    return p.stdout


def synth(text, voice):
    preset = PRESETS.get(voice) or PRESETS["jarvis"]
    key = (voice if voice in PRESETS else "jarvis", text)
    hit = CACHE.get(key)
    if hit is not None:
        CACHE.move_to_end(key)
        return hit
    with LOCK:
        if key[0] not in STYLES:
            STYLES[key[0]] = style_for(preset)
        samples, sr = KOKORO.create(text, voice=STYLES[key[0]], speed=preset["speed"], lang=preset["lang"])
    mp3 = encode(samples, sr, preset["depth"])
    CACHE[key] = mp3
    while len(CACHE) > 60:
        CACHE.popitem(last=False)
    return mp3


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/voices":
            self._send(200, json.dumps({"voices": [{"id": k, "label": v["label"]} for k, v in PRESETS.items()]}).encode())
        elif self.path == "/health":
            self._send(200, json.dumps({"ok": True, "cached": len(CACHE)}).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self):
        if self.path != "/tts":
            self._send(404, b"{}")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
            text = str(req.get("text") or "").strip()[:MAX_CHARS]
            if not text:
                self._send(400, b'{"detail":"no text"}')
                return
            t = time.time()
            mp3 = synth(text, str(req.get("voice") or "jarvis"))
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(mp3)))
            self.send_header("X-Gen-Seconds", "%.2f" % (time.time() - t))
            self.end_headers()
            self.wfile.write(mp3)
        except Exception as e:
            self._send(500, json.dumps({"detail": type(e).__name__ + ": " + str(e)[:160]}).encode())


if __name__ == "__main__":
    for phrase in ("One moment.", "Yes.", "Sorry, I could not do that."):   # warm the model and the common phrases
        try:
            synth(phrase, "jarvis")
        except Exception as e:
            print("warm failed", phrase, e, flush=True)
    print("jarvis voice ready on", PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
