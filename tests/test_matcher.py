from gpu_alerts.matcher import ProductMatcher


def test_matches_tracker_from_product_hint_tokens() -> None:
    matcher = ProductMatcher()

    match = matcher.match("GL.iNet GL-MT6000 (Flint 2) WiFi 6 Router", product_hint="glinet-flint-2")

    assert match is not None
    assert match.product_family == "glinet-flint-2"
    assert match.canonical_model.startswith("glinet-flint-2-")


def test_ignores_other_model_when_hint_tokens_do_not_match() -> None:
    matcher = ProductMatcher()

    match = matcher.match("GL.iNet Slate AX GL-AXT1800 Router", product_hint="glinet-flint-2")

    assert match is None


def test_matches_equivalent_variant_titles_to_same_generic_key() -> None:
    matcher = ProductMatcher()

    first = matcher.match(
        "ASUS GeForce RTX 5070 Ti TUF OC 16GB",
        product_hint="rtx-5070-ti",
        include_terms=["rtx", "5070", "ti"],
    )
    second = matcher.match(
        "Asus RTX5070Ti TUF OC GDDR7",
        product_hint="rtx-5070-ti",
        include_terms=["rtx", "5070", "ti"],
    )

    assert first is not None
    assert second is not None
    assert first.product_family == "rtx-5070-ti"
    assert first.canonical_model == second.canonical_model


def test_distinguishes_variant_specific_remaining_tokens() -> None:
    matcher = ProductMatcher()

    inspire = matcher.match(
        "MSI GeForce RTX 5070 Ti Inspire 3X OC 16GB",
        product_hint="rtx-5070-ti",
        include_terms=["rtx", "5070", "ti"],
    )
    expert = matcher.match(
        "MSI GeForce RTX 5070 Ti Expert OC 16GB",
        product_hint="rtx-5070-ti",
        include_terms=["rtx", "5070", "ti"],
    )

    assert inspire is not None
    assert expert is not None
    assert inspire.canonical_model != expert.canonical_model


def test_include_terms_can_enforce_specific_tracker_scope() -> None:
    matcher = ProductMatcher()

    match = matcher.match(
        "PlayStation 5 Slim Konsole",
        product_hint="ps5-pro",
        include_terms=["ps5", "pro"],
    )

    assert match is None


def test_product_hint_without_include_terms_requires_all_hint_tokens() -> None:
    matcher = ProductMatcher()

    match = matcher.match("MSI GeForce RTX 5070 12GB", product_hint="rtx-5070-ti")

    assert match is None


def test_match_returns_none_without_tracker_context() -> None:
    matcher = ProductMatcher()

    match = matcher.match("Gigabyte GeForce RTX 5070 Ti Eagle OC SFF 16GB")

    assert match is None
