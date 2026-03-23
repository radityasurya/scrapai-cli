import asyncio

import click


@click.command()
@click.argument("html_file")
@click.option("--test", default=None, help="Test a specific CSS selector")
@click.option("--find", default=None, help="Find elements by keyword")
def analyze(html_file, test, find):
    """Analyze HTML for CSS selector discovery"""
    from services.analyzer_service import AnalyzerService

    service = AnalyzerService()

    if test:
        result = asyncio.run(service.test_selector(html_file, test))
        _render_test_selector(result)
    elif find:
        result = asyncio.run(service.find_by_keyword(html_file, find))
        _render_find_by_keyword(result)
    else:
        result = asyncio.run(service.analyze_html(html_file))
        _render_analyze_html(result)


def _render_analyze_html(result):
    if not result["success"]:
        click.echo(f"❌ {result['error']}")
        return

    click.echo(f"📄 Analyzing: {result['html_file']}")
    click.echo(f"📊 HTML size: {result['html_size']} bytes")
    click.echo("\n💡 TIP: Use --find 'keyword' to search for specific elements\n")

    click.echo("=" * 60)
    click.echo("🏷️  HEADERS (h1, h2)")
    click.echo("=" * 60)
    headers_by_tag = {}
    for header in result["headers"]:
        headers_by_tag.setdefault(header["tag"], []).append(header)
    for tag in ["h1", "h2"]:
        headers = headers_by_tag.get(tag, [])
        if headers:
            click.echo(f"\n{tag.upper()} - Found {len(headers)}:")
            for i, header in enumerate(headers[:5], 1):
                click.echo(f"  [{i}] {header['selector']}")
                click.echo(f"      Text: {header['text']}")

    click.echo("\n" + "=" * 60)
    click.echo("📝 CONTENT CONTAINERS")
    click.echo("=" * 60)
    for i, container in enumerate(result["content_containers"], 1):
        click.echo(f"\n  [{i}] {container['selector']}")
        click.echo(f"      Size: {container['size']} chars")
        click.echo(f"      Preview: {container['preview']}...")

    click.echo("\n" + "=" * 60)
    click.echo("📅 DATES")
    click.echo("=" * 60)
    for match in result["dates"]:
        click.echo(f"  {match['selector']}: {match['text']}")

    click.echo("\n" + "=" * 60)
    click.echo("✍️  AUTHORS")
    click.echo("=" * 60)
    for match in result["authors"]:
        click.echo(f"  {match['selector']}: {match['text']}")

    click.echo("\n" + "=" * 60)


def _render_test_selector(result):
    click.echo(f"\n🔍 Testing selector: {result['selector']}")
    click.echo("=" * 60)

    if not result["success"]:
        click.echo("❌ No elements found!")
        return

    click.echo(f"✓ Found {result['count']} element(s)\n")
    for i, match in enumerate(result["matches"], 1):
        click.echo(f"[{i}] {match['tag']}")
        click.echo(f"    Classes: {match['classes']}")
        click.echo(f"    Text ({len(match['text'])} chars): {match['text']}...")
        click.echo()


def _render_find_by_keyword(result):
    click.echo(f"\n🔎 Finding elements with keyword: '{result['keyword']}'")
    click.echo("=" * 60)

    if not result["success"]:
        click.echo(f"\n❌ No elements found with keyword '{result['keyword']}'")
        click.echo("\n💡 Try: 'price', 'rating', 'author', 'date', 'title'")
        return

    for match in result["matches"]:
        click.echo(f"\n  {match['tag']}{match['selector']}")
        click.echo(f"    Text: {match['text']}")
