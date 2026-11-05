"""Minimal client for local Ollama chat completions."""

import httpx


def explain_verified_summary(
    base_url: str,
    model: str,
    question: str,
    summary: dict[str, int],
) -> str:
    system_prompt = (
        "Anda adalah asisten analisis data berbahasa Indonesia. "
        "Jelaskan hanya ringkasan agregat terverifikasi yang diberikan. "
        "Jangan mengarang catatan, statistik, identitas, penyebab, atau "
        "hasil query. Jika ringkasan tidak cukup, nyatakan keterbatasannya. "
        "Korelasi bukan bukti identitas, kausalitas, atau pelanggaran."
    )
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Ringkasan PostgreSQL terverifikasi: {summary}\n"
                        f"Pertanyaan analis: {question}"
                    ),
                },
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    message = response.json().get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty chat response.")
    return content.strip()
