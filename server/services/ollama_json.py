"""Bounded non-streaming JSON calls, including explicit thinking control.

The installed LangChain adapter predates Ollama's thinking parameter. Keep
ReAct on its adapter, but JSON composition/review must receive final content.
"""
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import settings


class OllamaJSONClient:
    def __init__(self, model=None, num_predict=None):
        self.model = model or settings.ollama_model
        self.num_predict = int(num_predict or settings.llm_max_output_tokens)

    def invoke(self, messages):
        roles = {"human": "user", "system": "system", "ai": "assistant"}
        body = {"model": self.model, "stream": False, "format": "json",
                "messages": [{"role": roles[m.type], "content": m.content} for m in messages],
                "options": {"temperature": 0, "num_predict": self.num_predict}}
        if settings.ollama_json_disable_thinking:
            body["think"] = False
        request = Request(settings.ollama_base_url.rstrip("/") + "/api/chat",
                          data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
                raw = response.read(131073)
            if len(raw) > 131072:
                raise ValueError("Oversized JSON provider response")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("done") is not True or result.get("done_reason") == "length":
                raise ValueError("Incomplete JSON provider response")
            message = result.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Missing JSON provider final content")
            return SimpleNamespace(content=content)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError(f"JSON provider HTTP status {status}") from None
        except (URLError, TimeoutError):
            raise RuntimeError("JSON provider unavailable or timed out") from None
