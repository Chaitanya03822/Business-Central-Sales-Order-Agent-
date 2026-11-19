
import re
import unicodedata
from rapidfuzz import fuzz


def normalize_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.casefold()

    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    aliases = {
        "pvt": "private",
        "ltd": "limited",
        "co": "company",
        "corp": "corporation",
        "inc": "incorporated",
    }

    value = " ".join(
        aliases.get(word, word)
        for word in value.split()
    )

    return value


def compare_text(left, right):
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)

    if not normalized_left or not normalized_right:
        score = 0.0
    else:
        score = float(
            fuzz.ratio(normalized_left, normalized_right)
        )

    return {
        "score": round(score, 2),
        "normalized_left": normalized_left,
        "normalized_right": normalized_right,
        "exact_after_normalization": (
            bool(normalized_left)
            and normalized_left == normalized_right
        ),
    }


def classify_match(
    score,
    auto_threshold=95.0,
    review_threshold=85.0,
):
    if score >= auto_threshold:
        return "HIGH_CONFIDENCE"

    if score >= review_threshold:
        return "MANUAL_REVIEW"

    return "NO_MATCH"
