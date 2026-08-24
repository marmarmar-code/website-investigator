from website_investigator.standards import parse_ads_txt, parse_security_txt


def test_parses_ads_txt_without_storing_comments_or_invalid_lines():
    result = parse_ads_txt(
        b"""
        # public advertising declarations
        seller.example, account-1, DIRECT, authority-1
        reseller.example, account-2, RESELLER
        invalid line
        """
    )

    assert result.available
    assert [entry.seller_domain for entry in result.entries] == [
        "seller.example",
        "reseller.example",
    ]
    assert [entry.relationship for entry in result.entries] == ["DIRECT", "RESELLER"]
    assert result.invalid_lines == 1


def test_parses_public_security_contacts_and_policy():
    result = parse_security_txt(
        b"""
        Contact: mailto:security@example.com
        Contact: https://example.com/security
        Policy: https://example.com/security-policy
        Expires: 2027-01-01T00:00:00Z
        Unknown: ignored
        """
    )

    assert result.available
    assert result.contacts == [
        "mailto:security@example.com",
        "https://example.com/security",
    ]
    assert result.policy == ["https://example.com/security-policy"]
    assert result.expires == "2027-01-01T00:00:00Z"
    assert result.invalid_lines == 1
