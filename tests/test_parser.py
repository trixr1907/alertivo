from __future__ import annotations

from gpu_alerts.collectors.parser import ParsedHtmlCollectorMixin
from gpu_alerts.config import ParserConfig, SourceConfig


class DummyCollector(ParsedHtmlCollectorMixin):
    def __init__(self, config: SourceConfig) -> None:
        self._config = config
        self.name = config.name


def test_geizhals_category_article_can_parse_title_price_stock_and_link() -> None:
    config = SourceConfig(
        name="geizhals_rtx5070ti_all_models",
        type="http",
        enabled=True,
        url="https://geizhals.de/?cat=gra16_512&xf=9816_03+05+18+-+RTX+5070+Ti",
        interval_seconds=90,
        timeout_seconds=20,
        shop="geizhals",
        source="geizhals",
        scope="aggregator",
        product_hint="rtx-5070-ti",
        parser=ParserConfig(
            mode="list",
            item_selector="article",
            title_selector="h3 a",
            price_selector="__self__",
            price_regex=r"ab\s*€\s*([0-9\.\,]+)",
            link_selector="h3 a",
            stock_selector="__self__",
            stock_in_texts=["lagernd beim Händler"],
            stock_out_texts=["derzeit keine angebote"],
        ),
    )
    collector = DummyCollector(config)
    html = """
    <html>
      <body>
        <article>
          <h3>
            <a href="msi-geforce-rtx-5070-ti-16g-inspire-3x-oc-a3445170.html">
              MSI GeForce RTX 5070 Ti 16G Inspire 3X OC, 16GB GDDR7
            </a>
          </h3>
          <div>7 Angebote</div>
          <div>ab <a href="msi-geforce-rtx-5070-ti-16g-inspire-3x-oc-a3445170.html#offerlist">€ 989,00</a></div>
          <note>lagernd beim Händler</note>
        </article>
      </body>
    </html>
    """

    observations = collector.parse_html(html)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.title.startswith("MSI GeForce RTX 5070 Ti 16G Inspire 3X OC")
    assert str(observation.price) == "989.00"
    assert observation.in_stock is True
    assert observation.url == "https://geizhals.de/msi-geforce-rtx-5070-ti-16g-inspire-3x-oc-a3445170.html"


def test_billiger_tile_can_parse_title_price_and_link() -> None:
    config = SourceConfig(
        name="billiger_rtx5070ti_search",
        type="http",
        enabled=True,
        url="https://www.billiger.de/search?searchstring=rtx+5070+ti",
        interval_seconds=90,
        timeout_seconds=20,
        shop="billiger",
        source="billiger",
        scope="aggregator",
        product_hint="rtx-5070-ti",
        parser=ParserConfig(
            mode="list",
            item_selector="[data-test-item-view-tile]",
            title_selector="a[title]",
            price_selector="[data-bde-price]",
            link_selector="a[title]",
        ),
    )
    collector = DummyCollector(config)
    html = """
    <div data-test-item-view-tile>
      <a href="/products/5199560289-gigabyte-geforce-rtx-5070-ti-16-gb-gddr7" title="Gigabyte GeForce RTX 5070 Ti 16 GB GDDR7"></a>
      <div data-bde-price><strong><span>ab</span> 899,90 €*</strong></div>
    </div>
    """

    observations = collector.parse_html(html)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.title == "Gigabyte GeForce RTX 5070 Ti 16 GB GDDR7"
    assert str(observation.price) == "899.90"
    assert observation.url == "https://www.billiger.de/products/5199560289-gigabyte-geforce-rtx-5070-ti-16-gb-gddr7"


def test_kleinanzeigen_ad_can_parse_title_price_and_link() -> None:
    config = SourceConfig(
        name="kleinanzeigen_mt6000_under_150",
        type="http",
        enabled=True,
        url="https://www.kleinanzeigen.de/s-multimedia-elektronik/mt6000/k0c161",
        interval_seconds=45,
        timeout_seconds=20,
        shop="kleinanzeigen",
        source="classifieds",
        scope="shop_search",
        product_hint="glinet-flint-2",
        parser=ParserConfig(
            mode="list",
            item_selector="article.aditem",
            title_selector="h2 a",
            price_selector="__self__",
            link_selector="h2 a",
            stock_selector="__self__",
            stock_in_texts=["Direkt kaufen", "VB", "€"],
        ),
    )
    collector = DummyCollector(config)
    html = """
    <article class="aditem" data-href="/s-anzeige/gl-inet-flint-2-router-gl-mt6000-/3335938565-225-27120">
      <h2 class="text-module-begin">
        <a href="/s-anzeige/gl-inet-flint-2-router-gl-mt6000-/3335938565-225-27120">GL.iNet Flint 2 Router (GL-MT6000)</a>
      </h2>
      <div>105 € VB</div>
    </article>
    """

    observations = collector.parse_html(html)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.title == "GL.iNet Flint 2 Router (GL-MT6000)"
    assert str(observation.price) == "105"
    assert observation.in_stock is True
    assert observation.url == "https://www.kleinanzeigen.de/s-anzeige/gl-inet-flint-2-router-gl-mt6000-/3335938565-225-27120"
