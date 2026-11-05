import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    title: str
    text: str

    @property
    def search_text(self) -> str:
        return f"{self.title}. {self.text}"


def _sections(markdown: str) -> list:
    stack: list = []
    sections, body = [], []

    def flush():
        text = "\n".join(body).strip()
        if text:
            sections.append((" > ".join(stack), text))
        body.clear()

    for line in markdown.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            del stack[level - 1:]
            stack.append(m.group(2).strip())
        else:
            body.append(line)
    flush()
    return sections


def _split_long(text: str, max_chars: int, overlap_chars: int) -> list:
    if len(text) <= max_chars:
        return [text]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if s.strip()]
    pieces, current = [], ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            tail = tail[tail.find(" ") + 1:] if tail and " " in tail else tail
            current = (tail + " " + sentence).strip()
        else:
            current = (current + " " + sentence).strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(doc: str, markdown: str, max_chars: int = 700, overlap_chars: int = 100) -> list:
    chunks = []
    for title, text in _sections(markdown):
        for piece in _split_long(text, max_chars, overlap_chars):
            chunks.append(Chunk(id=f"{doc}#{len(chunks)}", doc=doc, title=title or doc, text=piece))
    return chunks


def load_corpus(folder: Path) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(Path(folder).glob("*.md"))}


def chunk_corpus(corpus: dict, max_chars: int = 700, overlap_chars: int = 100) -> list:
    out = []
    for name, text in corpus.items():
        out.extend(chunk_markdown(name, text, max_chars, overlap_chars))
    return out


def corpus_hash(corpus: dict, max_chars: int = 700, overlap_chars: int = 100) -> str:
    h = hashlib.sha256()
    h.update(f"{max_chars}:{overlap_chars}".encode())
    for name in sorted(corpus):
        h.update(name.encode())
        h.update(corpus[name].encode())
    return h.hexdigest()[:16]
