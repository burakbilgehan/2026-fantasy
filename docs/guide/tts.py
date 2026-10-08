"""Turn a guide narration file into one MP3 with Google Cloud TTS (Chirp3-HD, Turkish).

Usage: python3 docs/guide/tts.py docs/guide/narration/00-giris.txt [--voice Charon] [--out data/guide/00-giris.mp3]

The narration file is plain text. Paragraphs are separated by blank lines.
The API key is read at runtime from ~/projects/youtube/yt-pipeline/.env (GOOGLE_CLOUD_API_KEY); it is never copied here.
Chunks are cut at paragraph (then sentence) boundaries under the 5000-byte request limit.
MP3 chunks from the same encoder are joined by plain byte concatenation (no ffmpeg on this machine).
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

ENV = Path.home() / "projects/youtube/yt-pipeline/.env"
LIMIT = 4500  # bytes per request, below Google's 5000
# Chirp 3 HD: first 1M characters per month free, then 30 USD per 1M (verified, cloud.google.com/text-to-speech/pricing).
LEDGER = Path("data/guide/tts_ledger.tsv")  # month, file, chars sent
MONTH_CAP = 900_000  # stop before the free tier ends; other projects may use the same key


def api_key() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("GOOGLE_CLOUD_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"GOOGLE_CLOUD_API_KEY missing in {ENV}")


def chunks(text: str) -> list[str]:
    paras = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        pieces = [p] if len(p.encode()) <= LIMIT else re.split(r"(?<=[.!?])\s+", p)
        for piece in pieces:
            cand = f"{cur}\n\n{piece}" if cur else piece
            if len(cand.encode()) <= LIMIT:
                cur = cand
            else:
                out.append(cur)
                cur = piece
    if cur:
        out.append(cur)
    return out


def synth(text: str, voice: str, key: str, rate: float) -> bytes:
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "tr-TR", "name": f"tr-TR-Chirp3-HD-{voice}"},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
    }
    # curl, not urllib: this python.org build has no CA bundle.
    r = subprocess.run(
        ["curl", "-sS", "--fail-with-body", "-m", "180", "-H", "Content-Type: application/json", "--data-binary", "@-",
         f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"],
        input=json.dumps(body).encode(), capture_output=True,
    )
    if r.returncode:
        sys.exit(f"Google TTS failed: {r.stdout.decode()[:500]} {r.stderr.decode()[:300]}")
    data = json.loads(r.stdout)
    if not data.get("audioContent"):
        sys.exit("Google TTS returned empty audioContent")
    return base64.b64decode(data["audioContent"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("narration")
    ap.add_argument("--voice", default="Charon")
    ap.add_argument("--rate", type=float, default=1.25)
    ap.add_argument("--out")
    a = ap.parse_args()
    src = Path(a.narration)
    out = Path(a.out) if a.out else Path("data/guide") / f"{src.stem}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    key = api_key()
    parts = chunks(src.read_text())
    month = __import__("datetime").date.today().strftime("%Y-%m")
    used = sum(int(r.split("\t")[2]) for r in (LEDGER.read_text().splitlines() if LEDGER.exists() else [])
               if r.startswith(month))
    need = sum(len(c) for c in parts)
    if used + need > MONTH_CAP:
        sys.exit(f"STOP: {used:,} chars used this month + {need:,} > cap {MONTH_CAP:,}")
    audio = b""
    for i, c in enumerate(parts, 1):
        audio += synth(c, a.voice, key, a.rate)
        with LEDGER.open("a") as f:
            f.write(f"{month}\t{src.name}\t{len(c)}\n")
        print(f"  chunk {i}/{len(parts)} ok", flush=True)
    out.write_bytes(audio)
    print(f"{out} {len(audio) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
