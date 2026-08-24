from __future__ import annotations

import re

from .models import AdsEntry, AdsTxtObservation, SecurityTxtObservation

ADS_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
SECURITY_FIELDS = {
    "acknowledgments": "acknowledgments",
    "canonical": "canonical",
    "contact": "contacts",
    "encryption": "encryption",
    "expires": "expires",
    "hiring": "hiring",
    "policy": "policy",
    "preferred-languages": "preferred_languages",
}


def parse_ads_txt(body: bytes, *, limit: int = 5_000) -> AdsTxtObservation:
    result = AdsTxtObservation(available=True)
    for raw_line in body.decode("utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            result.invalid_lines += 1
            continue
        seller_domain = parts[0].lower().rstrip(".")
        relationship = parts[2].upper()
        if (
            not ADS_DOMAIN.fullmatch(seller_domain)
            or not parts[1]
            or relationship not in {"DIRECT", "RESELLER"}
        ):
            result.invalid_lines += 1
            continue
        if len(result.entries) >= limit:
            result.truncated = True
            continue
        result.entries.append(
            AdsEntry(
                seller_domain=seller_domain,
                publisher_account_id=parts[1][:300],
                relationship=relationship,
                certification_authority_id=parts[3][:300] if len(parts) > 3 and parts[3] else None,
            )
        )
    return result


def parse_security_txt(body: bytes, *, limit_per_field: int = 100) -> SecurityTxtObservation:
    result = SecurityTxtObservation(available=True)
    for raw_line in body.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        field, separator, value = line.partition(":")
        destination = SECURITY_FIELDS.get(field.strip().lower())
        value = value.strip()
        if not separator or not destination or not value:
            result.invalid_lines += 1
            continue
        if destination == "expires":
            result.expires = value[:500]
            continue
        values = getattr(result, destination)
        if len(values) < limit_per_field and value not in values:
            values.append(value[:2_048])
    return result
