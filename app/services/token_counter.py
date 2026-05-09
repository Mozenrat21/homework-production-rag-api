import tiktoken


ENCODING_NAME = "cl100k_base"


def count_tokens(text: str) -> int:
    """
    Approximate token counter.

    Для cost tracking у ДЗ:
    - input tokens;
    - output tokens;
    - estimated cost.
    """
    if not text:
        return 0

    encoding = tiktoken.get_encoding(ENCODING_NAME)
    return len(encoding.encode(text))