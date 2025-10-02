"""Unit tests for PIIMasker"""

import pytest
from core.policies.pii_masker import PIIMasker, create_pii_masker


class TestPIIMasker:
    """Test suite for PIIMasker"""

    def test_mask_pii_ssn(self):
        """Test SSN masking"""
        text = "My SSN is 123-45-6789"
        masked = PIIMasker.mask_pii(text)

        assert "123-45-6789" not in masked
        assert "[REDACTED_SSN]" in masked

    def test_mask_pii_credit_card(self):
        """Test credit card masking"""
        text = "Card number: 1234567890123456"
        masked = PIIMasker.mask_pii(text)

        assert "1234567890123456" not in masked
        assert "[REDACTED_CREDIT_CARD]" in masked

    def test_mask_pii_email(self):
        """Test email masking"""
        text = "Contact me at user@example.com"
        masked = PIIMasker.mask_pii(text)

        assert "user@example.com" not in masked
        assert "[REDACTED_EMAIL]" in masked

    def test_mask_pii_phone(self):
        """Test phone number masking"""
        text = "Call +1-555-123-4567"
        masked = PIIMasker.mask_pii(text)

        assert "+1-555-123-4567" not in masked
        assert "[REDACTED_PHONE]" in masked

    def test_mask_pii_ip_address(self):
        """Test IP address masking"""
        text = "Server IP: 192.168.1.1"
        masked = PIIMasker.mask_pii(text)

        assert "192.168.1.1" not in masked
        assert "[REDACTED_IP_ADDRESS]" in masked

    def test_mask_pii_multiple(self):
        """Test masking multiple PII types"""
        text = "Email: user@test.com, Phone: 555-1234, SSN: 123-45-6789"
        masked = PIIMasker.mask_pii(text)

        assert "user@test.com" not in masked
        assert "555-1234" not in masked
        assert "123-45-6789" not in masked
        assert "[REDACTED_EMAIL]" in masked
        assert "[REDACTED_PHONE]" in masked
        assert "[REDACTED_SSN]" in masked

    def test_contains_pii_true(self):
        """Test PII detection returns True"""
        assert PIIMasker.contains_pii("Contact: user@example.com")
        assert PIIMasker.contains_pii("SSN: 123-45-6789")
        assert PIIMasker.contains_pii("Phone: +1-555-1234")

    def test_contains_pii_false(self):
        """Test PII detection returns False"""
        assert not PIIMasker.contains_pii("No PII in this text")
        assert not PIIMasker.contains_pii("Just regular content")

    def test_detect_pii_types(self):
        """Test PII type detection"""
        text = "Email: user@test.com, SSN: 123-45-6789"
        types = PIIMasker.detect_pii_types(text)

        assert "email" in types
        assert "ssn" in types
        assert len(types) == 2

    def test_validate_domain_trust_whitelisted(self):
        """Test trust score for whitelisted domains"""
        trust = PIIMasker.validate_domain_trust("https://techcrunch.com/article")
        assert trust == 1.0

        trust = PIIMasker.validate_domain_trust("https://wired.com/news")
        assert trust == 1.0

        trust = PIIMasker.validate_domain_trust("https://reuters.com/story")
        assert trust == 1.0

    def test_validate_domain_trust_blacklisted(self):
        """Test trust score for blacklisted domains"""
        trust = PIIMasker.validate_domain_trust("https://spam.com/bad")
        assert trust == 0.0

        trust = PIIMasker.validate_domain_trust("https://phishing.net/scam")
        assert trust == 0.0

    def test_validate_domain_trust_unknown(self):
        """Test trust score for unknown domains"""
        trust = PIIMasker.validate_domain_trust("https://unknown-site.com/page")
        assert trust == 0.7  # Penalty for unknown

    def test_validate_domain_trust_none(self):
        """Test trust score for None URL"""
        trust = PIIMasker.validate_domain_trust(None)
        assert trust == 0.7

    def test_is_safe_domain_safe(self):
        """Test safe domain check"""
        assert PIIMasker.is_safe_domain("https://techcrunch.com/article")
        assert PIIMasker.is_safe_domain("https://example.com/page")
        assert PIIMasker.is_safe_domain(None)

    def test_is_safe_domain_unsafe(self):
        """Test unsafe domain check"""
        assert not PIIMasker.is_safe_domain("https://spam.com/bad")
        assert not PIIMasker.is_safe_domain("https://phishing.net/scam")

    def test_sanitize_evidence_removes_blacklisted(self):
        """Test evidence sanitization removes blacklisted domains"""
        evidence = [
            {"title": "Good Source", "url": "https://techcrunch.com/article", "snippet": "Clean content"},
            {"title": "Bad Source", "url": "https://spam.com/bad", "snippet": "Spam content"},
            {"title": "Another Good", "url": "https://wired.com/news", "snippet": "More clean content"}
        ]

        sanitized = PIIMasker.sanitize_evidence(evidence)

        assert len(sanitized) == 2
        assert all(e["url"] != "https://spam.com/bad" for e in sanitized)

    def test_sanitize_evidence_masks_pii(self):
        """Test evidence sanitization masks PII"""
        evidence = [
            {
                "title": "Contact us at user@example.com",
                "url": "https://techcrunch.com/article",
                "snippet": "Call +1-555-1234 for more info"
            }
        ]

        sanitized = PIIMasker.sanitize_evidence(evidence)

        assert len(sanitized) == 1
        assert "user@example.com" not in sanitized[0]["title"]
        assert "+1-555-1234" not in sanitized[0]["snippet"]
        assert "[REDACTED_EMAIL]" in sanitized[0]["title"]
        assert "[REDACTED_PHONE]" in sanitized[0]["snippet"]

    def test_calculate_confidence_penalty_all_whitelisted(self):
        """Test confidence penalty with all whitelisted sources"""
        evidence = [
            {"url": "https://techcrunch.com/a"},
            {"url": "https://wired.com/b"},
            {"url": "https://reuters.com/c"}
        ]

        penalty = PIIMasker.calculate_confidence_penalty(evidence)
        assert penalty == 1.0  # No penalty

    def test_calculate_confidence_penalty_mixed(self):
        """Test confidence penalty with mixed sources"""
        evidence = [
            {"url": "https://techcrunch.com/a"},  # 1.0
            {"url": "https://unknown.com/b"},     # 0.7
            {"url": "https://wired.com/c"}        # 1.0
        ]

        penalty = PIIMasker.calculate_confidence_penalty(evidence)
        # Average: (1.0 + 0.7 + 1.0) / 3 = 0.9
        assert 0.85 < penalty < 0.95

    def test_calculate_confidence_penalty_empty(self):
        """Test confidence penalty with no evidence"""
        penalty = PIIMasker.calculate_confidence_penalty([])
        assert penalty == 0.5  # Low confidence

    def test_mask_pii_preserves_structure(self):
        """Test that masking preserves text structure"""
        text = "Name: John Doe, Email: john@example.com, Age: 30"
        masked = PIIMasker.mask_pii(text)

        # Should still have commas and structure
        assert "Name: John Doe" in masked
        assert "Age: 30" in masked
        assert "john@example.com" not in masked


def test_create_pii_masker():
    """Test factory function"""
    masker = create_pii_masker()
    assert isinstance(masker, PIIMasker)
