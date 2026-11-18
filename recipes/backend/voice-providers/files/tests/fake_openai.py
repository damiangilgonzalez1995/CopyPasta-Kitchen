"""OpenAI at the HTTP level: the real SDK runs, only the network is replaced (`httpx.MockTransport`).
That way the tests check what is actually sent (multipart file name, model, language, prompt)."""

import json
import re

import httpx

FILENAME = re.compile(rb'filename="([^"]+)"')
FIELD = re.compile(rb'name="([a-z_\[\]]+)"\r\n\r\n([^\r]*)\r\n')


class FakeOpenAI:
    """`status` != 200 -> that error for every call. `verbose_segments` -> whisper verbose_json answer."""

    def __init__(self, *, text: str = "hola mundo", status: int = 200, body: dict | None = None, segments: list[dict] | None = None) -> None:
        self.text = text
        self.status = status
        self.body = body
        self.segments = segments
        self.requests: list[dict] = []

    @property
    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        content = request.read()
        record = {"path": request.url.path, "content_type": request.headers.get("content-type", "")}
        if record["content_type"].startswith("multipart/form-data"):
            record["filename"] = (FILENAME.search(content) or [None, b""])[1].decode()
            record["fields"] = {k.decode(): v.decode() for k, v in FIELD.findall(content)}
        else:
            record["json"] = json.loads(content or b"{}")
        self.requests.append(record)
        if self.status != 200:
            return httpx.Response(self.status, json=self.body or {"error": {"message": "nope", "type": "x", "param": None, "code": None}})
        if request.url.path.endswith("/audio/transcriptions"):
            if record["fields"].get("response_format") == "verbose_json":
                return httpx.Response(200, json={"text": self.text, "language": "spanish", "duration": 1.0, "segments": self.segments or []})
            return httpx.Response(200, json={"text": self.text})
        if request.url.path.endswith("/audio/speech"):
            return httpx.Response(200, content=b"ID3fake-mp3-bytes", headers={"content-type": "audio/mpeg"})
        return httpx.Response(404, json={"error": {"message": "unknown path"}})
