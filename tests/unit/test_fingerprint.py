"""Unit tests for the candidate-person fingerprint helper.

The fingerprint is the stability key for reject-memory: rejecting a pair
should remain effective even after re-extraction perturbs variant order or
duplicates entries. Genuinely new evidence (a new variant) should change
the fingerprint so the rejection no longer applies.
"""

from __future__ import annotations

from pipeline.stage5_link.fingerprint import candidate_fingerprint


def test_determinism() -> None:
    assert candidate_fingerprint("申侯", ["申侯", "申伯"]) == candidate_fingerprint(
        "申侯", ["申侯", "申伯"]
    )


def test_length_and_charset() -> None:
    fp = candidate_fingerprint("申侯", ["申侯"])
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_variant_order_does_not_matter() -> None:
    a = candidate_fingerprint("褒姒", ["褒姒", "褒妃", "褒娰"])
    b = candidate_fingerprint("褒姒", ["褒娰", "褒姒", "褒妃"])
    assert a == b


def test_duplicate_variants_dont_matter() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申侯", ["申侯", "申伯", "申伯", "申侯"])
    assert a == b


def test_new_variant_changes_fingerprint() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申侯", ["申侯", "申伯", "申国君"])
    assert a != b


def test_name_change_changes_fingerprint() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申伯", ["申侯", "申伯"])
    assert a != b


def test_empty_variants_is_valid() -> None:
    fp = candidate_fingerprint("申侯", [])
    assert len(fp) == 16
