from datetime import datetime, timezone
from pathlib import Path


SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "forget previous instructions",
    "disregard previous instructions",
    "reveal your system prompt",
    "show your system prompt",
    "print your system prompt",
    "show system message",
    "developer message",
    "jailbreak",
    "act as dan",
]


LOG_PATH = Path("logs/suspicious_requests.log")


def find_suspicious_pattern(message: str) -> str | None:
    """
    Повертає pattern, якщо повідомлення схоже на prompt injection.
    Якщо все ок — повертає None.
    """
    normalized_message = message.lower().strip()

    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in normalized_message:
            return pattern

    return None


def is_suspicious_input(message: str) -> bool:
    """
    Простий boolean wrapper.
    """
    return find_suspicious_pattern(message) is not None


def log_suspicious_request(message: str, reason: str) -> None:
    """
    Логує підозрілий запит у файл.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    created_at_utc = datetime.now(timezone.utc).isoformat()
    safe_message = message.replace("\n", " ").replace("\r", " ")

    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(
            f"{created_at_utc}\t{reason}\t{safe_message}\n"
        )