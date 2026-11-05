import math
import re
from collections import Counter

TOKEN = re.compile(r"[a-z0-9]+")
STOP = frozenset("a an and are as at be but by do does for from how i if in is it its my of on or so than that the their then there this to was what when where which who why will with you your can".split())


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> list:
    return [stem(t) for t in TOKEN.findall(text.lower()) if t not in STOP]


class BM25:
    def __init__(self, texts: list, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list:
        terms = tokenize(query)
        out = []
        for d, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in terms:
                tf = d.get(t, 0)
                if tf:
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / (self.avg or 1.0)))
            out.append(s)
        return out
