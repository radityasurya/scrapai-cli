# Named Callbacks & Custom Fields

Extract custom fields from any structured data - products, jobs, listings, forums. Not limited to articles.

## When to Use

**Use callbacks for:**
- E-commerce (products, prices, ratings)
- Job boards (titles, companies, salaries)
- Real estate (properties, prices, features)
- Forums (posts, authors, replies)
- Any non-article structured data

**Use parse_article for:**
- News, blogs, documentation
- Content with title/content/author/date structure

**Use parse_job for:**
- Job posting detail pages
- Pages with JobPosting JSON-LD schema
- Sites where you want automatic extraction without custom selectors

## Built-in Callbacks

### parse_article

Extracts article-style content using newspaper4k and trafilatura. Use for news, blogs, and documentation.

```json
{
  "rules": [{"allow": ["/article/.*"], "callback": "parse_article"}]
}
```

No `callbacks` config needed - it's built-in.

### parse_job

Extracts job posting data using JSON-LD schema and HTML heuristics. Extracts: title, company, location, description, employment_type, posted_date, closing_date, remote, job_id.

```json
{
  "rules": [{"allow": ["/jobs/.*"], "callback": "parse_job"}]
}
```

**Extraction order:**
1. `JobPosting` JSON-LD structured data
2. HTML heuristics for common job field patterns
3. Optional custom selectors via `JOB_CUSTOM_SELECTORS` setting

**With custom selectors:**
```json
{
  "rules": [{"allow": ["/jobs/.*"], "callback": "parse_job"}],
  "settings": {
    "JOB_CUSTOM_SELECTORS": {
      "title": "h1.job-title",
      "company": "span.company-name",
      "location": "span.location",
      "description": "div.job-description"
    }
  }
}
```

**Listing to detail flow:**
```json
{
  "callbacks": {
    "parse_job_listing": {
      "iterate": {
        "selector": "article.job-card",
        "follow": {
          "url": {"css": "a::attr(href)"},
          "callback": "parse_job"
        }
      },
      "extract": {
        "listing_salary": {"css": "span.salary::text"}
      }
    }
  }
}
```

The listing fields are merged with the job detail fields from `parse_job`.

## Basic Structure

```json
{
  "rules": [{"allow": ["/product/.*"], "callback": "parse_product"}],
  "callbacks": {
    "parse_product": {
      "extract": {
        "name": {"css": "h1::text"},
        "price": {
          "css": "span.price::text",
          "processors": [
            {"type": "strip"},
            {"type": "regex", "pattern": "\\$([\\d.]+)"},
            {"type": "cast", "to": "float"}
          ]
        }
      }
    }
  }
}
```

## Field Extraction

**Selectors:**
- CSS: `{"css": "h1::text"}`, `{"css": "img::attr(src)"}`
- XPath: `{"xpath": "//h1/text()"}`
- Lists: `{"css": "li::text", "get_all": true}`

**Nested lists:**
```json
{
  "reviews": {
    "type": "nested_list",
    "selector": "div.review",
    "extract": {
      "author": {"css": "span.author::text"},
      "rating": {"css": "span.stars::attr(data-rating)", "processors": [{"type": "cast", "to": "int"}]},
      "comment": {"css": "p.text::text"}
    }
  }
}
```

Max depth: 3 levels.

## Processors

8 available - see [processors.md](processors.md):

- `strip` - Remove whitespace
- `replace` - Replace substring
- `regex` - Extract with pattern
- `cast` - Convert type (int, float, bool, str)
- `join` - Join list to string
- `default` - Fallback value
- `lowercase` - Convert to lowercase
- `parse_datetime` - Parse dates (stores as ISO strings)

**Chain processors:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "regex", "pattern": "\\$([\\d.]+)"},
  {"type": "cast", "to": "float"}
]}
```

## Iterate: Listing-to-Detail Workflows

For sites where data spans two pages — e.g., a ranking table (listing) links to individual detail pages — use `iterate` to loop over rows, extract per-row fields, and follow links to detail pages with that data passed along.

**Use iterate when:**
- Rankings/directories where rank lives on the listing page but details live on linked pages
- Search results where you need data from both the result snippet and the full page
- Any listing → detail pattern where you need fields from both pages

### Structure

```json
{
  "callbacks": {
    "parse_listing": {
      "iterate": {
        "selector": "table tr:has(td.rank)",
        "follow": {
          "url": {"css": "td.name a::attr(href)"},
          "callback": "parse_detail"
        }
      },
      "extract": {
        "rank": {"css": "td.rank::text", "processors": [{"type": "strip"}, {"type": "cast", "to": "int"}]},
        "name": {"css": "td.name a::text"}
      }
    },
    "parse_detail": {
      "extract": {
        "website": {"css": "a.website::attr(href)"},
        "description": {"css": "div.about::text"}
      }
    }
  }
}
```

### How it works

1. `parse_listing` loops over each row matching `selector`
2. For each row, `extract` fields are pulled from the **row element** (not full page)
3. The `follow.url` selector extracts the link from the row
4. A request is made to that URL with `callback: "parse_detail"`
5. Extracted row fields are passed via Scrapy `meta` as `listing_data`
6. `parse_detail` receives the response, merges `listing_data` into its item, then extracts its own fields

The final item contains fields from **both** pages (listing + detail) at the top level.

### Optional: url_context

Extract fields from the **page URL** using regex (useful when URL contains data like country codes):

```json
{
  "iterate": {
    "selector": "table tr",
    "url_context": {
      "country_code": {"regex": "/(\\w{2})/"},
      "state": {"regex": "/\\w{2}/([\\w-]+)\\.htm"}
    },
    "follow": {
      "url": {"css": "td a::attr(href)"},
      "callback": "parse_detail"
    }
  }
}
```

`url_context` fields are extracted once per page and included in every row's `listing_data`.

### Key details

- `extract` in iterate mode uses the **row** as scope (not full response)
- `url_context` regex must have exactly **one capture group**
- `follow.callback` must reference a defined callback (or `parse_article`)
- Rows without a matching URL are silently skipped
- Items are only counted when the detail callback yields (not the iterate callback)
- `extract` is optional in iterate callbacks (you can follow without extracting row fields)

## Templates

Complete working examples in `templates/`:

- **E-commerce:** `templates/spider-ecommerce.json`
- **Job boards:** `templates/spider-jobs.json`
- **Real estate:** `templates/spider-realestate.json`

Use as starting points - adjust selectors to match target site.

## Reserved Names

Never use: `parse_article`, `parse_start_url`, `start_requests`, `from_crawler`, `closed`, `parse`

## Storage

- Standard fields (url, title, content, author, published_date) → DB columns
- Custom fields → `metadata_json` column
- `show` command displays custom fields
- Exports flatten custom fields to top-level columns/keys

## Workflow

1. Analyze sample page: `./scrapai analyze page.html`
2. Identify fields and discover selectors: `./scrapai analyze page.html --test "h1::text"`
3. Build callback config with processors
4. Test on multiple pages to verify selectors work
5. Import and test: `./scrapai crawl spider --limit 5 --project proj`

## Common Patterns

**Extract price:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "regex", "pattern": "\\$([\\d,.]+)"},
  {"type": "replace", "old": ",", "new": ""},
  {"type": "cast", "to": "float"}
]}
```

**Extract boolean:**
```json
{"processors": [
  {"type": "lowercase"},
  {"type": "regex", "pattern": "(yes|true|available)"},
  {"type": "cast", "to": "bool"}
]}
```

**Handle missing fields:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "default", "default": null}
]}
```

## Troubleshooting

**Field returns None:**
- Test selector: `./scrapai analyze page.html --test "selector"`
- Check if page needs `--browser` (for JS-rendered or Cloudflare-protected sites)
- Verify processor chain (failed processor may return None)

**Wrong type in output:**
- Add `cast` processor: `{"type": "cast", "to": "float"}`

**Rule references undefined callback:**
- Add callback to `callbacks` dict
- Or use `callback: null` for navigation-only rules
