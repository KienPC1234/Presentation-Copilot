"""Keep lexical branch context on code chunks; hints are not an AST proof."""
import re

from langchain_core.documents import Document

BOUNDARY = re.compile(r"(?m)^[ \t]*(?:case\s+(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)(?P=quote)|(?P<default>default))\s*:")
MARKDOWN_HEADER = re.compile(r"(?m)^#{1,6}[ \t]+")


def split_case_scopes(documents):
    result = []
    for document in documents:
        text = document.page_content
        boundaries = list(BOUNDARY.finditer(text))
        if not boundaries:
            result.append(document)
            continue
        cursor = 0
        for index, match in enumerate(boundaries):
            if cursor < match.start():
                result.append(Document(page_content=text[cursor:match.start()], metadata=dict(document.metadata)))
            end = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(text)
            # A following Markdown section is a different source excerpt,
            # not part of the preceding switch branch.
            heading = MARKDOWN_HEADER.search(text, match.end(), end)
            if heading:
                end = heading.start()
            metadata = dict(document.metadata)
            metadata["scope_hint"] = "switch case " + (match.group("name") or "default")
            result.append(Document(page_content=text[match.start():end], metadata=metadata))
            cursor = end
        if cursor < len(text):
            result.append(Document(page_content=text[cursor:], metadata=dict(document.metadata)))
    return result
