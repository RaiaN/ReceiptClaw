from __future__ import annotations

import re
from abc import ABC, abstractmethod
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path

from receipt_processor.models import ReceiptPayload


class ReceiptSource(ABC):
    @abstractmethod
    def read(self) -> ReceiptPayload:
        raise NotImplementedError


class ManualTextInput(ReceiptSource):
    def __init__(self, text: str):
        self.text = text

    def read(self) -> ReceiptPayload:
        return ReceiptPayload(source="manual_text_input", raw_content=self.text.strip())


class EmailInboxAdapter(ReceiptSource):
    def __init__(self, eml_path: str | Path):
        self.eml_path = Path(eml_path)

    def read(self) -> ReceiptPayload:
        message = BytesParser(policy=policy.default).parsebytes(self.eml_path.read_bytes())
        html = ""
        text = ""
        for part in message.walk():
            content_type = part.get_content_type()
            try:
                payload = part.get_content()
            except Exception:
                continue
            if content_type == "text/plain":
                text += str(payload)
            elif content_type == "text/html":
                html += str(payload)
        content = text.strip() or _strip_html(html)
        return ReceiptPayload(source="email_inbox_adapter", raw_content=content.strip())


def _strip_html(value: str) -> str:
    without_style = re.sub(r"<style.*?>.*?</style>", " ", value, flags=re.I | re.S)
    without_script = re.sub(r"<script.*?>.*?</script>", " ", without_style, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", without_script)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text

