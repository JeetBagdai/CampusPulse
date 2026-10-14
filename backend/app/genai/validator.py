"""Numeric validator: the LLM may only use numbers the engine computed.

Every number in generated text must match (within tolerance) a number in the
facts given to the model; IDs such as WO-12 / E-201 / B1-1WR / BIN-05 must survive
translation unchanged.
"""
import re
from typing import Iterable

_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯", "01234567890123456789")
_NUM = re.compile(r"(?<![\w\-])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
_ID = re.compile(r"\b(?:WO|ISS|BIN|TKT)-\d+\b|\b[A-Z][A-Z0-9]?-\d{1,2}(?:\d{2}|WR)\b")


def normalize(text: str) -> str:
    return (text or "").translate(_NATIVE_DIGITS)


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(normalize(text)):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def facts_numbers(obj) -> set[float]:
    """Collect every number appearing anywhere in a facts structure."""
    nums: set[float] = set()
    if isinstance(obj, bool):
        return nums
    if isinstance(obj, (int, float)):
        nums.add(float(obj))
        nums.add(float(round(obj)))
        nums.add(round(float(obj), 1))
    elif isinstance(obj, str):
        nums.update(numbers_in(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            nums |= facts_numbers(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            nums |= facts_numbers(v)
    return nums


def check_numbers(text: str, allowed: Iterable[float], tol: float = 0.01) -> list[float]:
    """Returns numbers in `text` not backed by `allowed`. Small integers (<=10) are always allowed."""
    allowed = list(allowed)
    bad = []
    for n in numbers_in(text):
        if n <= 10 and n == int(n):
            continue
        if not any(abs(n - a) <= max(tol * abs(a), 0.051) for a in allowed):
            bad.append(n)
    return bad


def ids_in(text: str) -> set[str]:
    return set(_ID.findall(normalize(text)))


def check_ids(source: str, translated: str) -> set[str]:
    """IDs present in source but missing from translation."""
    return ids_in(source) - ids_in(translated)
