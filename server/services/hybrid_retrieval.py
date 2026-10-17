"""Identifier-aware lexical anchors alongside dense search, not a relevance proof."""
import math
import re
from collections import defaultdict

TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
STOP = frozenset({"which", "there", "these", "those", "their", "about", "would", "should", "could",
                  "where", "before", "after", "project", "evidence", "source", "provided", "return", "trong"})


def anchors(text):
    return {term.casefold() for term in TOKEN.findall(text) if (len(term) >= 5 or "_" in term) and term.casefold() not in STOP}


class IdentifierIndex:
    def __init__(self, documents):
        self.documents = documents
        self.postings = defaultdict(set)
        self.declarations = defaultdict(set)
        for index, document in enumerate(documents):
            for term in anchors(document.page_content):
                self.postings[term].add(index)
            for name in re.findall(r"\b(?:function|def)\s+([A-Za-z_]\w*)", document.page_content):
                self.declarations[name.casefold()].add(index)

    def search(self, query, limit):
        scores = defaultdict(float)
        for term in anchors(query):
            matches = self.postings.get(term, ())
            weight = math.log((len(self.documents) + 1) / (len(matches) + 1))
            for index in matches:
                scores[index] += weight
            for index in self.declarations.get(term, ()):
                scores[index] += 1.0  # A definition is more informative than a call site.
        ranked = sorted((i for i in scores if scores[i] > 0), key=lambda i: (-scores[i], i))[:limit]
        return [self.documents[i] for i in ranked]


def merge_results(semantic, lexical, limit):
    result, seen = [], set()
    # Keep both retrieval routes instead of replacing dense retrieval entirely.
    for index in range(max(len(semantic), len(lexical))):
        for sequence in (lexical, semantic):
            if index >= len(sequence):
                continue
            document = sequence[index]
            identity = (document.metadata.get("source_path"), document.metadata.get("page"), document.page_content)
            if identity not in seen:
                result.append(document)
                seen.add(identity)
                if len(result) >= limit:
                    return result
    return result
