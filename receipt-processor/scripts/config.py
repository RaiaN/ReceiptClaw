import os

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

IMAGE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # best-effort structured outputs
TEXT_MODEL = "openai/gpt-oss-20b"  # strict structured outputs

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
