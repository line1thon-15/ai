"""모델 출력에서 JSON 객체 하나를 꺼내는 공용 함수."""
import json
import re


def parse_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    for candidate in (text, (re.search(r"\{.*\}", text, re.S) or [None])[0]):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        return data if isinstance(data, dict) else None
    return None


def clean_text(value) -> str:
    """공백 정리 + 감싼 따옴표 제거. 문자열이 아니면 TypeError."""
    if not isinstance(value, str):
        raise TypeError("not a string")
    text = re.sub(r"\s+", " ", value).strip()
    # 양끝이 모두 따옴표일 때만 벗긴다 ("방장 '지니'" 처럼 끝에만 있는 따옴표는 둔다)
    if len(text) >= 2 and text[0] in QUOTES and text[-1] in QUOTES:
        text = text[1:-1].strip()
    return text


QUOTES = "\"'“”‘’"


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def count_sentences(text: str, min_len: int = 0) -> int:
    """문장 수. min_len 을 주면 '네!', '알겠어요.'처럼 그보다 짧은 말은 세지 않는다."""
    return len([s for s in split_sentences(text) if len(s) >= min_len])


def first_sentences(text: str, n: int, min_len: int = 6) -> str:
    """앞에서부터 n 문장만 남긴다. '와!'처럼 min_len 보다 짧은 감탄은 문장 수에 세지 않는다
    (세면 "와! 정말 잘했어요!"만 남고 무엇을 잘했는지가 잘린다)."""
    sents = split_sentences(text)
    kept, counted = [], 0
    for s in sents:
        if counted >= n:
            break
        kept.append(s)
        if len(s) >= min_len:
            counted += 1
    return " ".join(kept) if len(kept) < len(sents) else text
