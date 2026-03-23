__all__ = ["DatabaseSpider", "SitemapDatabaseSpider"]


def __getattr__(name):
    if name == "DatabaseSpider":
        from .database_spider import DatabaseSpider

        return DatabaseSpider
    if name == "SitemapDatabaseSpider":
        from .sitemap_spider import SitemapDatabaseSpider

        return SitemapDatabaseSpider
    raise AttributeError(f"module 'spiders' has no attribute {name!r}")
