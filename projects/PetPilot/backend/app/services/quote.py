def is_valid_quote(quote: str, text: str) -> bool:
    """quote 必须完整、连续地落在原文里（不拼接、不改写）。"""
    if not quote or not text:
        return False
    return quote.strip() in text


def strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    return s
