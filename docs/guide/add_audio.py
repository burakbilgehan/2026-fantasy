"""Put an audio player under the header of every episode page that has an MP3 in data/guide/.

Idempotent: an existing player block is replaced. The published artifact serves the MP3 at audio/<slug>.mp3.
Usage: python3 docs/guide/add_audio.py
"""
import re
from pathlib import Path

GUIDE = Path(__file__).parent
AUDIO = GUIDE.parents[1] / "data/guide"
def players(slug: str) -> str:
    """Audio tags for one episode. Long episodes are split into -1/-2 parts (artifact limit 15 MB per file)."""
    parts = sorted(AUDIO.glob(f"{slug}-[0-9].mp3"))
    if parts:
        return "".join(f'<span class="meta">Kısım {i}</span><audio controls preload="none" src="audio/{p.name}"></audio>'
                       for i, p in enumerate(parts, 1))
    return f'<audio controls preload="none" src="audio/{slug}.mp3"></audio>'


BLOCK = re.compile(r"<!-- audio -->.*?<!-- /audio -->\n?", re.S)

for page in sorted(GUIDE.glob("[0-9][0-9]-*.html")):
    html = BLOCK.sub("", page.read_text())
    mp3 = AUDIO / f"{page.stem}.mp3"
    if mp3.exists():
        player = (f'<!-- audio --><div class="audio"><span class="eyebrow">Sesli bölüm</span>'
                  f'{players(page.stem)}</div><!-- /audio -->\n')
        html = html.replace("</header>", "</header>\n" + player, 1)
    page.write_text(html)
    print(page.name, "audio" if mp3.exists() else "no audio")

# Index: a player per episode row, or a "hazırlanıyor" note and a disabled link when the page is not ready.
index = GUIDE / "index.html"
html = index.read_text()
def row(m: re.Match) -> str:
    slug = m.group(1)
    ready = (AUDIO / f"{slug}.mp3").exists()  # a page is published only once its audio is done
    mp3 = (AUDIO / f"{slug}.mp3").exists()
    inner = (players(slug) if mp3
             else '<span class="soon">Ses hazırlanıyor</span>')
    cls = "ep-row" if ready else "ep-row wait"
    body = re.sub(r"<!-- player -->.*?<!-- /player -->|<!-- player -->", f"<!-- player -->{inner}<!-- /player -->", m.group(2), count=1, flags=re.S)
    return f'<div class="{cls}" data-ep="{slug}">{body}</div>'
html = re.sub(r'<div class="ep-row(?: wait)?" data-ep="([^"]+)">(.*?)</div>', row, html, flags=re.S)
index.write_text(html)
