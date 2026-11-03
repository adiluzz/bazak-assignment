import hashlib
import math
import re

DIM = 384


def hash_embed(text: str, dim: int = DIM) -> list[float]:
    vector = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.md5(token.encode()).hexdigest()
        index = int(digest, 16) % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def embed_texts(texts: list[str], mode: str) -> list[list[float]]:
    if mode == "fastembed":
        from langchain_community.embeddings import FastEmbedEmbeddings

        model = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        return model.embed_documents(texts)
    return [hash_embed(text) for text in texts]


def embed_query(text: str, mode: str) -> list[float]:
    if mode == "fastembed":
        from langchain_community.embeddings import FastEmbedEmbeddings

        model = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        return model.embed_query(text)
    return hash_embed(text)
