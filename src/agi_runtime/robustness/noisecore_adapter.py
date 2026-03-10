import random
import re

VOWELS = set("aeiouAEIOU")
NOISE = ["#", "_", "~", "^"]


def encode_noisecore(text: str, level: int = 2) -> str:
    out = []
    for tok in re.findall(r"\s+|\S+", text):
        if tok.isspace() or not tok.isalpha():
            out.append(tok)
            continue
        v = sum(1 for c in tok if c in VOWELS)
        stem = "".join(c for c in tok if c not in VOWELS)
        if not stem:
            stem = tok[0]
        enc = f"{stem}{v}"
        if level >= 2 and len(enc) > 2 and random.random() < 0.5:
            i = random.randint(1, len(enc) - 1)
            enc = enc[:i] + random.choice(NOISE) + enc[i:]
        out.append(enc)
    return "".join(out)


def strip_noise(text: str) -> str:
    return text.replace("#", "").replace("_", "").replace("~", "").replace("^", "")


def decode_noisecore(text: str) -> str:
    # best-effort decode: remove noise tokens and vowel counts
    cleaned = strip_noise(text)
    cleaned = re.sub(r"([A-Za-z]+)\d+", r"\1", cleaned)
    return cleaned
