"""Turn an episode HTML page into the narration text the TTS voice reads.

The voice reads the page itself (user rule, 2026-10-07): every heading, paragraph, list item, note and player card,
in page order. Skipped: tables, the audio player, .meta lines and the header eyebrow. Chips are read as "Karar: ...",
score pips as "Hedef puanı beşte üç", the price line as short spoken sentences.
Numbers, dates, signs, %, $ and stat abbreviations are converted to spoken Turkish.

Usage: python3 docs/guide/narrate.py docs/guide/03-atlantic.html   (writes docs/guide/narration/03-atlantic.txt)
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
ORD = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci", "altı": "altıncı",
       "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu", "on": "onuncu", "yirmi": "yirminci",
       "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
       "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü", "bin": "bininci", "sıfır": "sıfırıncı"}
MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TEAMS = {"ATL": "Atlanta", "BOS": "Boston", "BKN": "Brooklyn", "CHA": "Charlotte", "CHI": "Chicago", "CLE": "Cleveland",
         "DAL": "Dallas", "DEN": "Denver", "DET": "Detroit", "GSW": "Golden State", "HOU": "Houston", "IND": "Indiana",
         "LAC": "Clippers", "LAL": "Lakers", "MEM": "Memphis", "MIA": "Miami", "MIL": "Milwaukee", "MIN": "Minnesota",
         "NOP": "New Orleans", "NYK": "New York", "OKC": "Oklahoma City", "ORL": "Orlando", "PHI": "Philadelphia",
         "PHX": "Phoenix", "POR": "Portland", "SAC": "Sacramento", "SAS": "San Antonio", "TOR": "Toronto", "UTA": "Utah",
         "WAS": "Washington"}
TERMS = [  # order matters: longer first
    (r"\bFG%", "saha içi yüzdesi"), (r"\bFT%", "serbest atış yüzdesi"), (r"\b3PTM\b", "üçlük"), (r"\b3PM\b", "üçlük"),
    (r"\b9-cat\b", "dokuz kategori"), (r"\b8-cat\b", "sekiz kategori"), (r"\bH2H\b", "kafa kafaya"),
    (r"\bMinus-1\b", "Minus bir"), (r"\bz-skor", "z skor"), (r"\bTO\b", "top kaybı"), (r"\bAST\b", "asist"),
    (r"\bREB\b", "ribaund"), (r"\bPTS\b", "sayı"), (r"\bSTL\b", "top çalma"), (r"\bST\b", "top çalma"),
    (r"\bBLK\b", "blok"), (r"\bFGA\b", "saha içi deneme"), (r"\bFTA\b", "serbest atış denemesi"),
    (r"\bFG\b", "saha içi"), (r"\bFT\b", "serbest atış"), (r"\bMPG\b", "maç başı dakika"), (r"\bGP\b", "maç sayısı"),
    (r"\bBN\b", "yedek"), (r"\bUSD\b", "dolar"),
]
SKIP_CLASSES = {"meta", "eyebrow", "audio", "tbl"}
BLOCKS = {"h1", "h2", "h3", "p", "li", "div", "article", "section", "header", "td", "th"}


def cardinal(n: int) -> str:
    if n == 0:
        return "sıfır"
    parts = []
    if n >= 1_000_000:
        parts.append(cardinal(n // 1_000_000) + " milyon")
        n %= 1_000_000
    if n >= 1000:
        k = n // 1000
        parts.append("bin" if k == 1 else cardinal(k) + " bin")
        n %= 1000
    if n >= 100:
        h = n // 100
        parts.append("yüz" if h == 1 else ONES[h] + " yüz")
        n %= 100
    if n >= 10:
        parts.append(TENS[n // 10])
        n %= 10
    if n:
        parts.append(ONES[n])
    return " ".join(parts)


def ordinal(n: int) -> str:
    words = cardinal(n).split()
    words[-1] = ORD.get(words[-1], words[-1])
    return " ".join(words)


def decimal(s: str) -> str:
    """'34,5' or '34.5' or '0,73' -> spoken."""
    ip, fp = re.split(r"[.,]", s)
    head = cardinal(int(ip))
    if not fp.strip("0"):
        return head
    if fp == "5":
        return f"{head} buçuk"
    lead = "sıfır " * (len(fp) - len(fp.lstrip("0")))
    return f"{head} virgül {lead}{cardinal(int(fp)) if fp.strip('0') else ''}".strip()


def number(tok: str) -> str:
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", tok):  # Turkish thousands: 1.888
        return cardinal(int(tok.replace(".", "")))
    if re.fullmatch(r"\d+[.,]\d+", tok):
        return decimal(tok)
    return cardinal(int(tok))


def speak(t: str) -> str:
    t = t.replace(" ", " ").replace("·", ",").replace("•", ",")
    # dates
    t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: f"{cardinal(int(m[3]))} {MONTHS[int(m[2])]}", t)
    t = re.sub(r"\b(\d{2})-(\d{2})\b(?=\)|,)", lambda m: f"{cardinal(int(m[2]))} {MONTHS[int(m[1])]}"
               if 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31 else m[0], t)
    # team codes and terms
    t = re.sub(r"\b(" + "|".join(TEAMS) + r")\b", lambda m: TEAMS[m[1]], t)
    for pat, rep in TERMS:
        t = re.sub(pat, rep, t)
    # money and percent
    t = re.sub(r"\$\s?(\d+(?:[.,]\d+)?)", lambda m: number(m[1]) + " dolar", t)
    t = re.sub(r"%\s?(\d+(?:[.,]\d+)?)", lambda m: "yüzde " + number(m[1]), t)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda m: "yüzde " + number(m[1]), t)
    # schedules and ranges: 3-4-4, 13-14
    t = re.sub(r"\b\d+(?:-\d+){2,}\b", lambda m: ", ".join(cardinal(int(x)) for x in m[0].split("-")), t)
    t = re.sub(r"\b(\d+)-(\d+)\b", lambda m: f"{cardinal(int(m[1]))} ile {cardinal(int(m[2]))}", t)
    # signs
    t = re.sub(r"(?<![\w])\+(\d)", r"artı \1", t)
    t = re.sub(r"(?<![\w])[-−](\d)", r"eksi \1", t)
    # ordinals: "13. sıra", "4.)" ; a number + period before a lowercase word or a closing paren
    t = re.sub(r"\b(\d+)\.(?=\s+[a-zçğıöşü(]|\)|,)", lambda m: ordinal(int(m[1])), t)
    # numbers with suffixes: 30'dan -> otuzdan
    t = re.sub(r"(\d+(?:[.,]\d+)?)'(\w+)", lambda m: number(m[1]) + m[2], t)
    t = re.sub(r"\d{1,3}(?:\.\d{3})+|\d+[.,]\d+(?=\D|$)|\d+", lambda m: number(m[0]), t)
    t = t.replace("$", " dolar").replace("%", " yüzde").replace("&", " ve ")
    t = t.replace("—", ", ").replace("–", ", ")
    t = re.sub(r"\s*[()\[\]{}]\s*", ", ", t).replace(" = ", " eşittir ")
    t = re.sub(r"\s*,\s*(,\s*)+", ", ", t)
    t = re.sub(r",\s*([.;:])", r"\1", t)
    t = re.sub(r"\s+([.,;:!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    return t


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.buf: list[str] = []
        self.stack: list[tuple[str, bool, str]] = []  # (tag, skipping, role)
        self.chips: list[str] = []
        self.prices: list[str] = []

    @property
    def skipping(self) -> bool:
        return any(s for _, s, _ in self.stack)

    def role(self) -> str:
        for _, _, r in reversed(self.stack):
            if r:
                return r
        return ""

    def flush(self):
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if text:
            if not text.endswith((".", "!", "?", ":")):
                text += "."
            self.out.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "img", "meta", "link", "hr", "source"):
            return
        cls = set((dict(attrs).get("class") or "").split())
        skip = tag in ("table", "style", "script", "title", "audio", "head", "nav") or bool(cls & SKIP_CLASSES)
        role = "chip" if "chip" in cls else "score" if "score" in cls else "prices" if "prices" in cls else ""
        if tag in BLOCKS and not self.skipping and not self.role():
            self.flush()
        self.stack.append((tag, skip, role))

    def handle_endtag(self, tag):
        if tag not in (t for t, _, _ in self.stack):  # stray end tag: ignore, do not unwind the stack
            return
        while self.stack:
            t, skip, role = self.stack.pop()
            if role == "prices" and self.prices:
                self.flush()
                self.out.append(" ".join(self.prices))
                self.prices = []
            if t == tag:
                break
        if tag in BLOCKS and not self.skipping and not self.role():
            if self.chips:
                self.flush()
                self.out.append("Karar: " + ", ".join(self.chips).replace("I", "ı").replace("İ", "i").lower() + ".")
                self.chips = []
            if tag in ("h1", "h2", "h3"):
                self.flush()

    def handle_data(self, data):
        if self.skipping:
            return
        role = self.role()
        if role == "chip":
            if data.strip():
                self.chips.append(data.strip())
        elif role == "score":
            filled = data.count("●")
            if filled or "○" in data:
                self.flush()
                self.out.append(f"Hedef puanı beşte {cardinal(filled)}.")
        elif role == "prices":
            m = re.match(r"\s*(.*?)\s*$", data)
            if m and m[1]:
                if self.prices and not self.prices[-1].endswith("."):
                    self.prices[-1] += " " + m[1] + "."
                else:
                    label = {"Bizim": "Bizim fiyat", "Piyasa": "Piyasa fiyatı", "9-cat sıra": "Dokuz kategori sırası",
                             "Points sıra": "Points sırası", "En fazla": "En fazla teklif"}.get(m[1], m[1])
                    self.prices.append(label)
        else:
            self.buf.append(data)


def narrate(html: str) -> str:
    p = Page()
    p.feed(html)
    p.flush()
    paras = [speak(x) for x in p.out]
    return "\n\n".join(x for x in paras if x.strip(" .,"))


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = src.parent / "narration" / f"{src.stem}.txt"
    out.parent.mkdir(exist_ok=True)
    text = narrate(src.read_text())
    out.write_text(text + "\n")
    print(out, len(text.split()), "words", len(text), "chars")
