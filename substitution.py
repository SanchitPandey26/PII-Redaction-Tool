from __future__ import annotations

import random
import re
from difflib import SequenceMatcher
from typing import Dict, Tuple

from faker import Faker


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


class Substitutor:
    def __init__(self, seed: int = 42):
        self.faker = Faker()
        Faker.seed(seed)
        random.seed(seed)

        # (label, normalized_original) -> fake replacement
        self._cache: Dict[Tuple[str, str], str] = {}
        # normalized-name-token -> (fake_first, fake_last), used for
        # name<->email correlation
        self._person_names: Dict[str, Tuple[str, str]] = {}

    # ------------------------------------------------------------------ #
    def substitute(self, original: str, label: str) -> str:
        key = (label, _normalize(original))
        if key in self._cache:
            return self._cache[key]

        handler = getattr(self, f"_fake_{label.lower()}", self._fake_generic)
        fake_value = handler(original)
        self._cache[key] = fake_value

        if label == "FULL_NAME":
            first, last = fake_value.split(" ", 1) if " " in fake_value else (fake_value, "")
            for tok in _tokens(original):
                self._person_names[tok] = (first, last)

        return fake_value

    # ------------------------------------------------------------------ #
    def _fake_full_name(self, original: str) -> str:
        return self.faker.name()

    def _fake_company_name(self, original: str) -> str:
        return self.faker.company()

    def _fake_address(self, original: str) -> str:
        return self.faker.address().replace("\n", ", ")

    def _fake_email_address(self, original: str) -> str:
        local = original.split("@", 1)[0]
        matched = self._match_known_person(local)
        if matched:
            first, last = matched
            return f"{first.lower()}.{last.lower()}@example.com"
        return self.faker.user_name() + "@example.com"

    def _fake_phone_number(self, original: str) -> str:
        # Keep it obviously-Indian and obviously-fake, matching the shape
        # of the source (mobile vs. landline), without echoing real digits.
        digits = re.sub(r"\D", "", original)
        if digits.startswith("91"):
            digits = digits[2:]
        if len(digits) <= 10:
            fake_number = "".join(str(random.randint(0, 9)) for _ in range(len(digits) or 10))
            return f"+91 {fake_number}"
        return f"+91 {self.faker.msisdn()[-10:]}"

    def _fake_ssn(self, original: str) -> str:
        return self.faker.ssn()

    def _fake_credit_card_number(self, original: str) -> str:
        return self.faker.credit_card_number()

    def _fake_ip_address(self, original: str) -> str:
        return self.faker.ipv6() if ":" in original else self.faker.ipv4()

    def _fake_date_of_birth(self, original: str) -> str:
        return self.faker.date_of_birth(minimum_age=25, maximum_age=70).strftime("%B %d, %Y")

    def _fake_generic(self, original: str) -> str:
        return "[REDACTED]"

    # ------------------------------------------------------------------ #
    def _match_known_person(self, email_local_part: str) -> Tuple[str, str] | None:
        candidate_tokens = re.findall(r"[a-z]+", email_local_part.lower())
        best, best_score = None, 0.0
        for tok in candidate_tokens:
            for known_tok, fake_pair in self._person_names.items():
                score = SequenceMatcher(None, tok, known_tok).ratio()
                if score > best_score:
                    best_score, best = score, fake_pair
        if best_score >= 0.8:
            return best
        return None
