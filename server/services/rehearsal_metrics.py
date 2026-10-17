"""Small speech metrics; none of these measure answer correctness."""
import re


def word_error_rate(reference, hypothesis):
    ref = re.findall(r"\w+", reference.casefold())
    hyp = re.findall(r"\w+", hypothesis.casefold())
    if not ref:
        raise ValueError("A nonempty verified reference is required")
    previous = list(range(len(hyp) + 1))
    for index, word in enumerate(ref, 1):
        current = [index]
        for j, observed in enumerate(hyp, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != observed)))
        previous = current
    return previous[-1] / len(ref)
