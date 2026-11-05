import argparse
import sys

from rag.chunker import load_corpus
from rag.embedders import LsaEmbedder, SentenceTransformerEmbedder
from rag.index import build_index
from services import rag_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the knowledge index used by the copilot.")
    parser.add_argument("--embedder", choices=["lsa", "st"], default="lsa", help="lsa works offline; st needs: pip install sentence-transformers")
    args = parser.parse_args()
    corpus = load_corpus(rag_service.KNOWLEDGE_DIR)
    if not corpus:
        print(f"no .md files in {rag_service.KNOWLEDGE_DIR}")
        sys.exit(1)
    try:
        embedder = LsaEmbedder() if args.embedder == "lsa" else SentenceTransformerEmbedder()
        index = build_index(corpus, embedder, rag_service.INDEX_DIR)
    except ImportError as exc:
        print(f"missing library: {exc}. For --embedder st run: pip install sentence-transformers")
        sys.exit(1)
    meta = index.meta
    print(f"indexed {len(corpus)} documents into {meta['n_chunks']} chunks | embedder {meta['embedder']} | vectors {meta['dim']}-d | saved to {rag_service.INDEX_DIR}")


if __name__ == "__main__":
    main()
