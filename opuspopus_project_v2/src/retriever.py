"""RAG retriever: gte embeddings if available, otherwise a pure-Python TF-IDF (no scipy/sklearn needed)."""
import hashlib, json, math, re
from collections import Counter
from src import config

STOP = set("a an the and or of to in on for with without by at from is are be been was were has have had "
           "not no any all this that these those as it its into than then who which their patients patient "
           "subjects participants must may will should can study trial".split())


def trial_doc(t):
    return (f"{t['title']}. Conditions: {', '.join(t.get('conditions', []))}. "
            f"{t.get('summary', '')} Inclusion: {' '.join(t['inclusion'][:8])}")


def _tokens(text):
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


class _TfIdf:
    def __init__(self, docs):
        toks = [_tokens(d) for d in docs]
        df = Counter(t for doc in toks for t in set(doc))
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in toks]

    def _vec(self, toks):
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * self.idf[t] for t, c in tf.items() if t in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {t: x / norm for t, x in v.items()}

    def scores(self, query):
        q = self._vec(_tokens(query))
        return [sum(w * d.get(t, 0) for t, w in q.items()) for d in self.vecs]


class Retriever:
    def __init__(self, trials):
        self.trials = trials
        self.mode = None
        self._model = None
        self._tfidf = None
        self.build()

    def build(self):
        docs = [trial_doc(t) for t in self.trials]
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
            sig = hashlib.md5((config.EMBED_MODEL + json.dumps([t["nct_id"] for t in self.trials])).encode()).hexdigest()
            idx_file = config.DATA / f"index_{sig[:10]}.npy"
            self._model = SentenceTransformer(config.EMBED_MODEL)
            if idx_file.exists():
                self.emb = np.load(idx_file)
            else:
                self.emb = self._model.encode(docs, normalize_embeddings=True, show_progress_bar=True)
                np.save(idx_file, self.emb)
            self.mode = f"Embeddings ({config.EMBED_MODEL.split('/')[-1]})"
        except Exception as e:  # not installed, DLL blocked by Windows policy, no internet...
            print(f"[retriever] embeddings unavailable ({type(e).__name__}); using built-in TF-IDF RAG")
            self._model = None
            self._tfidf = _TfIdf(docs)
            self.mode = "TF-IDF (built-in)"

    def search(self, query, k=5):
        if self._model is not None:
            q = self._model.encode([query], normalize_embeddings=True)[0]
            scores = [float(x) for x in (self.emb @ q)]
        else:
            scores = self._tfidf.scores(query)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self.trials[i], float(scores[i])) for i in order]
