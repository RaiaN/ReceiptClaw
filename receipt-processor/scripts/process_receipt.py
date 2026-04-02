#!/usr/bin/env python3
"""
Receipt processor – extracts structured data from a plain-text Tesco receipt
using the Groq LLM API and prints the result as JSON.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from groq import Groq
except ImportError:
    print(json.dumps({"error": "groq package not installed. Run: pip install groq"}))
    sys.exit(1)

from config import GROQ_API_KEY, TEXT_MODEL
from schema import RECEIPT_JSON_SCHEMA, SYSTEM_PROMPT


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
    parser = argparse.ArgumentParser(
        description="Extract structured data from a plain-text Tesco receipt."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", metavar="FILE", help="Path to a text file containing the receipt")
    group.add_argument("--inline", metavar="TEXT", help="Receipt text passed directly as a string")
    args = parser.parse_args()

    client = Groq(api_key=GROQ_API_KEY)

    try:
        if args.text:
            result = process_text(client, Path(args.text).read_text())
        else:
            result = process_text(client, args.inline)
    except Exception as e:
        result = {"error": str(e)}

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
