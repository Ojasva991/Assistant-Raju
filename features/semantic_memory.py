"""
features/semantic_memory.py
Smarter "recall" — finds the note most RELEVANT to what you're asking
about, instead of only ever returning the most recent note.

Two modes, chosen automatically:
  - "semantic" (better): uses sentence-transformers, an offline local
    embedding model. It understands meaning, so "what did I say about
    my exam" can match a note like "MST is on Friday" even without
    matching words. First run downloads a small model (~80MB) once —
    after that it's fully offline, no API calls, no per-query cost.
    Install: pip install sentence-transformers
  - "keyword" (automatic fallback): uses TF-IDF + cosine similarity
    from scikit-learn, which we already depend on. Matches on shared
    words/phrasing rather than meaning. Used automatically if
    sentence-transformers isn't installed — nothing breaks either way.

Everything here runs on your machine. No external API is called.
"""


class SemanticMemory:
    def __init__(self, memory):
        self.memory = memory
        self._model = None
        self.mode = "keyword"
        self._try_load_semantic_model()

    def _try_load_semantic_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self.mode = "semantic"
            print("[SemanticMemory] Loaded offline embedding model (semantic mode).")
        except Exception:
            self.mode = "keyword"
            print("[SemanticMemory] sentence-transformers not available, "
                  "using keyword-based fallback. (pip install sentence-transformers "
                  "for meaning-based search)")

    def find_relevant_note(self, query, user_id=0, limit=200):
        """Returns the note whose content is most relevant to `query`,
        or None if the user has no notes at all."""
        notes = self.memory.get_notes(limit=limit, user_id=user_id)
        if not notes:
            return None

        contents = [n["content"] for n in notes]
        if len(contents) == 1:
            return contents[0]

        if self.mode == "semantic":
            return self._semantic_best(query, contents)
        return self._keyword_best(query, contents)

    def _semantic_best(self, query, contents):
        import numpy as np
        query_vec = self._model.encode([query])[0]
        note_vecs = self._model.encode(contents)
        norms = np.linalg.norm(note_vecs, axis=1) * np.linalg.norm(query_vec) + 1e-8
        sims = (note_vecs @ query_vec) / norms
        best_idx = int(sims.argmax())
        return contents[best_idx]

    def _keyword_best(self, query, contents):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english").fit(contents + [query])
        note_vectors = vectorizer.transform(contents)
        query_vector = vectorizer.transform([query])
        sims = cosine_similarity(query_vector, note_vectors)[0]
        best_idx = int(sims.argmax())

        # If there's zero word overlap at all, TF-IDF similarity is 0 for
        # everything -- fall back to the most recent note rather than a
        # meaningless "best" match.
        if sims[best_idx] == 0:
            return contents[0]  # contents[0] is most recent (DB orders DESC)
        return contents[best_idx]
