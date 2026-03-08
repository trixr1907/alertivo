from gpu_alerts.matcher import ProductMatcher


def test_matches_flint_2_variants() -> None:
    matcher = ProductMatcher()

    match = matcher.match("GL.iNet GL-MT6000 (Flint 2) WiFi 6 Router")

    assert match is not None
    assert match.product_family == "glinet-flint-2"
    assert match.canonical_model == "glinet-flint-2-gl-mt6000"


def test_ignores_other_glinet_models() -> None:
    matcher = ProductMatcher()

    match = matcher.match("GL.iNet Slate AX GL-AXT1800 Router")

    assert match is None


def test_matches_rtx_5070_ti_variants_to_same_key() -> None:
    matcher = ProductMatcher()

    first = matcher.match("ASUS GeForce RTX 5070 Ti TUF OC 16GB")
    second = matcher.match("Asus RTX5070Ti TUF OC GDDR7")

    assert first is not None
    assert second is not None
    assert first.product_family == "rtx-5070-ti"
    assert first.canonical_model == second.canonical_model


def test_distinguishes_inspire_and_expert_variants() -> None:
    matcher = ProductMatcher()

    inspire = matcher.match("MSI GeForce RTX 5070 Ti Inspire 3X OC 16GB")
    expert = matcher.match("MSI GeForce RTX 5070 Ti Expert OC 16GB")

    assert inspire is not None
    assert expert is not None
    assert inspire.canonical_model != expert.canonical_model


def test_ignores_complete_pc_with_rtx_5070_ti_in_title() -> None:
    matcher = ProductMatcher()

    match = matcher.match("Gaming PC Ryzen 7 7800X3D RTX 5070 Ti 32GB RAM 2TB SSD")

    assert match is None


def test_ignores_komplettsystem_with_rtx_5070_ti() -> None:
    matcher = ProductMatcher()

    match = matcher.match("Komplettsystem Intel Core i7 RTX 5070 Ti 32GB DDR5 1TB SSD")

    assert match is None


def test_keeps_single_gpu_listing_without_pc_terms() -> None:
    matcher = ProductMatcher()

    match = matcher.match("Gigabyte GeForce RTX 5070 Ti Eagle OC SFF 16GB")

    assert match is not None
    assert match.product_family == "rtx-5070-ti"


def test_product_hint_does_not_force_non_ti_title() -> None:
    matcher = ProductMatcher()

    match = matcher.match("MSI GeForce RTX 5070 12GB", product_hint="rtx-5070-ti")

    assert match is None


def test_ignores_zbox_complete_system_even_with_ti_in_title() -> None:
    matcher = ProductMatcher()

    match = matcher.match("ZOTAC ZBOX RTX5070Ti Gamer 1TB SSD 32GB W11H")

    assert match is None
