from __future__ import annotations

import hashlib
import re
import unicodedata

from gpu_alerts.models import MatchResult


GPU_BRANDS = [
    "asus",
    "msi",
    "gigabyte",
    "zotac",
    "pny",
    "inno3d",
    "kfa2",
    "galax",
    "gainward",
    "palit",
    "manli",
    "colorful",
]

GPU_VARIANTS = [
    "amp extreme",
    "solid core",
    "gaming trio",
    "gaming oc",
    "windforce",
    "proart",
    "inspire",
    "expert",
    "master",
    "vanguard",
    "aero",
    "shadow",
    "strix",
    "solid",
    "trinity",
    "phoenix",
    "phoenix s",
    "ventus",
    "eagle",
    "prime",
    "tuf",
    "amp",
    "white",
    "black",
    "x3",
    "oc",
    "sff",
]

GENERIC_GPU_TOKENS = {
    "16gb",
    "aktiv",
    "bit",
    "displayport",
    "gddr7",
    "geforce",
    "grafikkarte",
    "hdmi",
    "nvidia",
    "oc",
    "pcie",
    "retail",
    "rtx",
    "ti",
    "x16",
}

COMPLETE_PC_PHRASES = [
    "gaming pc",
    "komplett pc",
    "komplettsystem",
    "fertig pc",
    "desktop pc",
    "pc system",
    "system pc",
    "all in one",
    "mini pc",
]

COMPLETE_PC_TERMS = {
    "pc",
    "computer",
    "desktop",
    "notebook",
    "laptop",
    "rechner",
    "tower",
    "workstation",
    "zbox",
    "barebone",
}

CPU_TERMS = [
    "intel core",
    "core ultra",
    "ryzen",
    "threadripper",
    "xeon",
    "athlon",
    "celeron",
    "pentium",
]

SYSTEM_SPEC_TERMS = {
    "ram",
    "ssd",
    "hdd",
    "nvme",
    "ddr4",
    "ddr5",
    "windows 11",
    "windows 10",
    "w11",
    "w11h",
    "win11",
    "win10",
}


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = normalized.replace("™", " ").replace("-", " ").replace("/", " ")
    normalized = re.sub(r"\b16gb\b|\bgddr7\b|\bgeforce\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _contains_any(haystack: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle in haystack]


def _fallback_hash(normalized_title: str) -> str:
    return hashlib.sha1(normalized_title.encode("utf-8")).hexdigest()[:12]


class ProductMatcher:
    def match(self, title: str, product_hint: str | None = None) -> MatchResult | None:
        normalized = normalize_title(title)

        if product_hint == "glinet-flint-2" or self._is_flint_2(normalized):
            return MatchResult(
                product_family="glinet-flint-2",
                canonical_model="glinet-flint-2-gl-mt6000",
                normalized_title=normalized,
            )

        is_rtx_5070_ti = self._is_rtx_5070_ti(normalized)
        # product_hint narrows product family, but never forces a false-positive title.
        if product_hint == "rtx-5070-ti" and not is_rtx_5070_ti:
            return None

        if is_rtx_5070_ti:
            if self._looks_like_complete_pc(normalized):
                return None
            brand = next((brand for brand in GPU_BRANDS if brand in normalized), "unknown")
            variants = _contains_any(normalized, GPU_VARIANTS)
            model_tokens = self._derive_model_tokens(normalized, brand)
            components = sorted(set(variants))
            for token in model_tokens:
                if token not in components:
                    components.append(token)
            variant_key = "-".join(components) if components else _fallback_hash(normalized)
            canonical_model = f"rtx-5070-ti-{brand}-{variant_key}"
            return MatchResult(
                product_family="rtx-5070-ti",
                canonical_model=canonical_model,
                normalized_title=normalized,
            )

        return None

    def _is_flint_2(self, normalized: str) -> bool:
        if "gl mt6000" in normalized or "glmt6000" in normalized:
            return True
        return "flint 2" in normalized and "gl inet" in normalized

    def _is_rtx_5070_ti(self, normalized: str) -> bool:
        compact = normalized.replace(" ", "")
        if "5070ti" not in compact:
            return False
        return "rtx" in compact or "geforce" in compact

    def _looks_like_complete_pc(self, normalized: str) -> bool:
        if any(phrase in normalized for phrase in COMPLETE_PC_PHRASES):
            return True

        tokens = set(normalized.split())
        if COMPLETE_PC_TERMS & tokens:
            return True

        has_cpu = any(term in normalized for term in CPU_TERMS)
        has_system_specs = any(term in normalized for term in SYSTEM_SPEC_TERMS)
        if has_cpu and has_system_specs:
            return True

        return False

    def _derive_model_tokens(self, normalized: str, brand: str) -> list[str]:
        tokens = []
        for token in normalized.split():
            if token == brand:
                continue
            if token in GENERIC_GPU_TOKENS:
                continue
            if token.isdigit():
                continue
            if "5070" in token:
                continue
            if len(token) <= 1:
                continue
            if token not in tokens:
                tokens.append(token)
        return tokens[:3]
