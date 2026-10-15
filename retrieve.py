"""KB retrieval: deterministic TF-IDF + cosine over kb_articles.json. No LLM, no hardcoded mapping.

Pure Python (no scikit-learn), so it runs anywhere with no compiled dependencies.
The query is the English processing text plus the classified intent (normalised metadata),
which is why retrieval runs after classification.
"""
import math
import re
from collections import Counter

TOP_K = 2
STOPWORDS = set("""a an the and or but if of to in on for with at by from is are was were be been being i my me we our you
your it its this that these those have has had do does did not no can could should would will so as up out
about after before again still now what which who why how when where there here than then just also very""".split())


def tokens(text):
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


def article_text(a):
    tags = " ".join(t.replace("_", " ") for t in a.get("tags", []))
    return f"{a['title']} {a['title']} {a.get('category', '')} {tags} {tags} {a['body']}"


class TfidfRetriever:
    def __init__(self, articles):
        self.articles = sorted(articles, key=lambda a: a["article_id"])  # input order never matters
        docs = [Counter(tokens(article_text(a))) for a in self.articles]
        n = len(docs)
        df = Counter(term for d in docs for term in d)
        self.idf = {term: math.log((1 + n) / (1 + c)) + 1 for term, c in df.items()}  # smoothed, as sklearn
        self.vectors = [self._vector(d) for d in docs]

    def _vector(self, counts):
        v = {t: (1 + math.log(c)) * self.idf[t] for t, c in counts.items() if t in self.idf}  # sublinear tf
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query, k=TOP_K):
        q = self._vector(Counter(tokens(query)))
        scores = [sum(w * d.get(t, 0.0) for t, w in q.items()) for d in self.vectors]
        ranked = sorted(range(len(self.articles)), key=lambda i: (-round(scores[i], 6), self.articles[i]["article_id"]))
        return [{"article_id": self.articles[i]["article_id"], "title": self.articles[i]["title"],
                 "score": round(scores[i], 4)} for i in ranked[:k]]


def build_query(pre, cls):
    return f"{pre['subject_for_processing']} {pre['message_for_processing']} {cls['intent'].replace('_', ' ')}"


def retrieve(preprocessed, classified, articles):
    retriever = TfidfRetriever(articles)
    cls_by_id = {c["ticket_id"]: c for c in classified}
    return [{"ticket_id": p["ticket_id"], "retrieved_articles": retriever.search(build_query(p, cls_by_id[p["ticket_id"]]))}
            for p in preprocessed]
