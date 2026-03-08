from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from gpu_alerts.config import SourceConfig
from gpu_alerts.models import OfferObservation
from gpu_alerts.parsing import parse_price, parse_stock


LOGGER = logging.getLogger(__name__)


class ParsedHtmlCollectorMixin:
    _config: SourceConfig
    name: str

    def parse_html(self, html: str) -> list[OfferObservation]:
        soup = BeautifulSoup(html, "html.parser")
        parser = self._config.parser
        if not parser:
            return []

        for selector in parser.remove_selectors:
            for tag in soup.select(selector):
                tag.decompose()

        if parser.mode == "single":
            observation = self._parse_single(soup)
            return [observation] if observation else []

        if parser.mode == "list":
            return self._parse_list(soup)

        raise ValueError(f"Unsupported parser mode: {parser.mode}")

    def _parse_single(self, soup: BeautifulSoup) -> OfferObservation | None:
        parser = self._config.parser
        title = self._extract_text(soup, parser.title_selector)
        price_text = self._extract_text(soup, parser.price_selector)
        stock_text = self._extract_text(soup, parser.stock_selector)
        url = self._config.url or ""
        link = self._extract_link(soup, parser.link_selector)
        if link:
            url = urljoin(self._config.url or "", link)

        if not title and price_text is None:
            return None

        return OfferObservation(
            shop=self._config.shop,
            source=self._config.source,
            scope=self._config.scope,
            title=title or self._config.name,
            url=url,
            price=parse_price(price_text, parser.price_regex),
            in_stock=parse_stock(stock_text, parser.stock_in_texts, parser.stock_out_texts),
            product_hint=self._config.product_hint,
            include_title_terms=list(self._config.include_title_terms),
            exclude_title_terms=list(self._config.exclude_title_terms),
            price_ceiling=self._config.price_ceiling,
            new_listing_price_below=self._config.new_listing_price_below,
            raw_payload={"price_text": price_text, "stock_text": stock_text},
        )

    def _parse_list(self, soup: BeautifulSoup) -> list[OfferObservation]:
        parser = self._config.parser
        items = soup.select(parser.item_selector or "")
        observations: list[OfferObservation] = []
        for item in items:
            if not isinstance(item, Tag):
                continue

            title = self._extract_text(item, parser.title_selector)
            price_text = self._extract_text(item, parser.price_selector)
            stock_text = self._extract_text(item, parser.stock_selector)
            link = self._extract_link(item, parser.link_selector)

            if not title:
                continue

            observations.append(
                OfferObservation(
                    shop=self._config.shop,
                    source=self._config.source,
                    scope=self._config.scope,
                    title=title,
                    url=urljoin(self._config.url or "", link or self._config.url or ""),
                    price=parse_price(price_text, parser.price_regex),
                    in_stock=parse_stock(stock_text, parser.stock_in_texts, parser.stock_out_texts),
                    product_hint=self._config.product_hint,
                    include_title_terms=list(self._config.include_title_terms),
                    exclude_title_terms=list(self._config.exclude_title_terms),
                    price_ceiling=self._config.price_ceiling,
                    new_listing_price_below=self._config.new_listing_price_below,
                    raw_payload={"price_text": price_text, "stock_text": stock_text},
                )
            )

        LOGGER.debug("Collector %s parsed %s observations", self.name, len(observations))
        return observations

    @staticmethod
    def _extract_text(node: BeautifulSoup | Tag, selector: str | None) -> str | None:
        if not selector:
            return None
        if selector == "__self__":
            return node.get_text(" ", strip=True)
        selected = node.select_one(selector)
        if not selected:
            return None
        text = selected.get_text(" ", strip=True)
        if text:
            return text
        for attr_name in ("title", "aria-label", "alt", "content", "value"):
            value = selected.get(attr_name)
            if value and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_link(node: BeautifulSoup | Tag, selector: str | None) -> str | None:
        if not selector:
            return None
        if selector == "__self__":
            href = node.get("href")
            return href.strip() if href else None
        selected = node.select_one(selector)
        if not selected:
            return None
        href = selected.get("href")
        return href.strip() if href else None
