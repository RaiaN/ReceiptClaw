#!/usr/bin/env python3
"""
Receipt processor – extracts structured data from a receipt image or text
using the Groq LLM API and prints the result as JSON.
"""

import argparse
import base64
import json
import sys
from pathlib import Path

try:
    from groq import Groq
except ImportError:
    print(json.dumps({"error": "groq package not installed. Run: pip install groq"}))
    sys.exit(1)

from config import GROQ_API_KEY, IMAGE_EXTENSIONS, IMAGE_MODEL, TEXT_MODEL
from schema import RECEIPT_JSON_SCHEMA, RECEIPT_JSON_SCHEMA_BEST_EFFORT, SYSTEM_PROMPT


def encode_image(path: str) -> tuple[str, str]:
    """Return (base64_data, media_type) for an image file."""
    ext = Path(path).suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), media_type


def process_image(client: Groq, image_path: str) -> dict:
    b64, media_type = encode_image(image_path)
    response = client.chat.completions.create(
        model=IMAGE_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    },
                    {"type": "text", "text": "Extract all data from this receipt."},
                ],
            },
        ],
        response_format={"type": "json_schema", "json_schema": RECEIPT_JSON_SCHEMA_BEST_EFFORT},
        temperature=0,
        max_tokens=1024,
    )
    return json.loads(response.choices[0].message.content)


def process_text(client: Groq, text: str) -> dict:
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_schema", "json_schema": RECEIPT_JSON_SCHEMA},
        temperature=0,
        max_tokens=1024,
    )
    # strict mode guarantees valid JSON — no JSONDecodeError possible here
    return json.loads(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser(description="Extract structured data from a receipt.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("image", nargs="?", help="Path to a receipt image file")
    group.add_argument("--text", metavar="FILE", help="Path to a text file containing the receipt")
    group.add_argument("--inline", metavar="TEXT", help="Receipt text passed directly as a string")
    args = parser.parse_args()

    client = Groq(api_key=GROQ_API_KEY)

    try:
        if args.image:
            path = args.image
            ext = Path(path).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                result = process_image(client, path)
            else:
                result = process_text(client, Path(path).read_text())
        elif args.text:
            result = process_text(client, Path(args.text).read_text())
        else:
            result = process_text(client, args.inline)
    except Exception as e:
        result = {"error": str(e)}

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
