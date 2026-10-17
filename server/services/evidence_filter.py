"""Exclude obvious prompt-control directives from retrieved evidence.

This narrow heuristic is not a complete prompt-injection defence. Documents
quoting attacks may also be excluded; callers must tolerate missing evidence.
"""
import logging
import re

logger = logging.getLogger(__name__)
_CONTROL_DIRECTIVE = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions"
    r"|reveal\s+(?:the\s+)?(?:hidden|system)\s+(?:instructions|prompt)"
    r"|bỏ\s+qua\s+(?:mọi\s+|tất cả\s+)?(?:chỉ dẫn|hướng dẫn)\s+(?:trước|hệ thống)",
    re.IGNORECASE,
)


def filter_evidence(chunks: list[str]) -> list[str]:
    result = []
    for chunk in chunks:
        if _CONTROL_DIRECTIVE.search(chunk):
            logger.warning("Excluded a retrieved chunk containing prompt-control directives")
        else:
            result.append(chunk)
    return result
