# seo-stack-mcp

<!-- mcp-name: io.github.Raffaele86/seo-stack-mcp -->

**The complete open-source SEO data stack for AI agents.** Google Search Console, Google Analytics 4, Bing Webmaster Tools and Microsoft Clarity in a single MCP server — with built-in analyst tools (cannibalization check, low-hanging fruit, content gap, weekly report), not just raw API wrappers.

Self-hosted, free, MIT. Works with Claude Desktop, Claude Code, Cursor, and any MCP client.

## Why this instead of N separate servers?

- **One install, one config** — instead of wiring up 4 different MCP servers with 4 auth setups.
- **Analyst tools included** — ask *"which queries are declining this month?"* or *"find my low-hanging-fruit keywords"* and get an answer computed server-side, not a raw data dump your agent has to crunch.
- **Sources are optional** — configure only what you use; tools appear only for configured sources.
- **Self-hosted** — your tokens stay on your machine. No third-party hosted gateway reading your Search Console.

## Quickstart (60 seconds)

Add to your MCP client config (Claude Desktop `claude_desktop_config.json`, Cursor `mcp.json`, or `claude mcp add`):

```json
{
  "mcpServers": {
    "seo-stack": {
      "command": "uvx",
      "args": ["seo-stack-mcp"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json",
        "GA4_PROPERTY_ID": "123456789",
        "BING_WEBMASTER_API_KEY": "your-key",
        "CLARITY_API_TOKEN": "your-token"
      }
    }
  }
}
```

Every env var is optional — set only the sources you want. That's it: restart your client and ask *"what are my top queries this week?"*.

To run the latest development version straight from GitHub, use `"args": ["--from", "git+https://github.com/Raffaele86/seo-stack-mcp", "seo-stack-mcp"]` instead.

### Credentials

| Source | What you need | Where to get it |
|---|---|---|
| GSC + GA4 | Service account JSON (recommended) → `GOOGLE_APPLICATION_CREDENTIALS` | [Google Cloud Console](https://console.cloud.google.com/) → create service account → enable Search Console API + Analytics Data API → add the SA email as a user in GSC / GA4 |
| GSC + GA4 (alt) | OAuth desktop client JSON → `SEO_STACK_OAUTH_CLIENT` | First run opens a browser for consent; refresh token cached in `~/.config/seo-stack-mcp/` |
| Bing | `BING_WEBMASTER_API_KEY` | [Bing Webmaster Tools](https://www.bing.com/webmasters/) → Settings → API access |
| Clarity | `CLARITY_API_TOKEN` | [Microsoft Clarity](https://clarity.microsoft.com/) → project → Settings → Data Export API |

Optional defaults: `GSC_SITE_URL`, `BING_SITE_URL` (so you don't repeat the site on every question).

## Tools

### Google Search Console (29 tools)

| Tool | Description |
|---|---|
| `gsc_bulk_inspect_urls` | Inspect multiple URLs in batch via the URL Inspection API. Max 50 URLs per call. |
| `gsc_bulk_request_indexing` | Request indexing for multiple URLs via the Google Indexing API. Max 50 URLs. |
| `gsc_cannibalization_check` | Find queries where multiple pages compete (keyword cannibalization). Shows queries with 2+ ranking pages. |
| `gsc_compare_periods` | Compare two periods: shows deltas of clicks, impressions, CTR and position per item. |
| `gsc_content_gap_analysis` | Content gap analysis: queries where the competitor ranks but you don't (or you are far behind). |
| `gsc_country_performance` | Performance by country: clicks, impressions, CTR and average position. Default: last 28 days. |
| `gsc_daily_stats` | Aggregated daily site statistics: clicks, impressions, CTR and average position per day. |
| `gsc_declining_queries` | Queries losing clicks/positions: compares last N days vs the equivalent previous period. |
| `gsc_delete_sitemap` | Remove a sitemap from Google Search Console. Requires write scope on the credentials. |
| `gsc_device_performance` | Compare performance across MOBILE vs DESKTOP vs TABLET. Default: last 28 days. |
| `gsc_indexing_status_summary` | Indexing status summary for multiple URLs: how many indexed, not indexed, and errored. |
| `gsc_inspect_url` | Inspect a URL via the Google Search Console URL Inspection API. |
| `gsc_keyword_opportunities` | Queries with high impressions but low CTR in position 5-20: optimization opportunities. |
| `gsc_list_sitemaps` | List all sitemaps of a site in Google Search Console. |
| `gsc_list_sites` | List all Google Search Console properties available to the configured credentials. |
| `gsc_low_hanging_fruit` | Queries in position 3-10 with high impression volume: small optimizations can push them into the top 3. |
| `gsc_page_trend` | Daily trend for a specific page over the last N days (default 90). |
| `gsc_pages_for_query` | Which pages rank for a specific query? Shows all pages with performance data. |
| `gsc_queries_for_page` | Which queries drive traffic to a specific page? Shows all keywords with performance data. |
| `gsc_query_trend` | Daily trend for a specific query over the last N days (default 90). |
| `gsc_request_indexing` | Request indexing of a URL via the Google Indexing API. |
| `gsc_rising_queries` | Rising queries: compares last N days vs the equivalent previous period. |
| `gsc_search_analytics` | Query Search Analytics: clicks, impressions, CTR and position for the requested dimensions. |
| `gsc_search_analytics_filtered` | Search Analytics with advanced filters. Filters: query_contains, query_regex, page_contains, page_regex, country (e.g. 'ita'), device (MOBILE/DESKTOP/TABLET). |
| `gsc_search_appearance` | Performance by SERP result type (rich snippet, video, FAQ, etc.). Default: last 28 days. |
| `gsc_submit_sitemap` | Submit a sitemap to Google Search Console. Requires write scope on the credentials. |
| `gsc_top_pages` | Top pages by clicks or impressions. order_by: clicks, impressions, ctr, position. Default: last 28 days. |
| `gsc_top_queries` | Top queries by clicks or impressions. order_by: clicks, impressions, ctr, position. Default: last 28 days. |
| `gsc_weekly_report` | Automatic weekly report: last 7 days vs previous 7 days metrics with deltas and top queries/pages. |

### Google Analytics 4 (10 tools)

| Tool | Description |
|---|---|
| `ga4_compare_periods` | Compare two periods with percentage delta on key metrics. |
| `ga4_conversion_paths` | User paths: acquisition source → landing page with sessions and users. |
| `ga4_events` | Top GA4 events with count and number of users. |
| `ga4_landing_pages` | Entry pages (landing pages) with sessions, users and bounce rate. |
| `ga4_overview` | Site overview: users, sessions, pageviews, bounce rate, average session duration. |
| `ga4_page_performance` | Detailed performance of a single page with device and source breakdown. |
| `ga4_realtime` | Realtime report: pages currently being viewed and active users. |
| `ga4_top_pages` | Top pages by traffic with full metrics (pageviews, users, duration, bounce rate). |
| `ga4_traffic_sources` | Traffic breakdown by source/medium (e.g. google/organic, direct/none). |
| `ga4_user_demographics` | User demographics breakdown: country, device, browser, language. |

### Bing Webmaster Tools (22 tools)

| Tool | Description |
|---|---|
| `bing_crawl_issues` | URLs with crawl problems (4xx/5xx errors, redirects, etc.). |
| `bing_crawl_stats` | Bing crawl statistics: crawled pages, errors, redirects, etc. |
| `bing_keyword` | Bing impression volume for an exact query (impressions + broad). |
| `bing_keyword_stats` | Historical statistics for a keyword on Bing: impressions and trend. |
| `bing_link_counts` | Pages with the highest number of backlinks according to Bing. |
| `bing_pages_for_query` | Pages that rank for a specific query on Bing. |
| `bing_queries_for_page` | Search queries that drive traffic to a specific page. |
| `bing_query_page_detail` | Detailed statistics for a specific query + page combination. |
| `bing_query_traffic` | Daily traffic trend for a specific query on Bing. |
| `bing_related_keywords` | Keywords related to a search term on Bing, with impression data. |
| `bing_sitemaps` | List all sitemaps/feeds submitted to Bing. |
| `bing_sites` | List all sites verified in the Bing Webmaster Tools account. |
| `bing_submission_quota` | Check the URL submission quota for Bing. |
| `bing_submit_sitemap` | Submit a new sitemap/feed to Bing. |
| `bing_submit_url` | Submit a URL to Bing for indexing. |
| `bing_submit_urls_batch` | Submit a batch of URLs to Bing for indexing (max 500). |
| `bing_top_pages` | Top pages on Bing with clicks, impressions and average position. |
| `bing_top_queries` | Top Bing search queries with clicks, impressions and average position. |
| `bing_traffic_stats` | Daily Bing traffic statistics: clicks and impressions over time. |
| `bing_url_info` | Indexing status of a specific URL on Bing. |
| `bing_url_links` | Inbound backlinks to a specific URL according to Bing. |
| `bing_url_traffic` | Traffic data for a specific URL on Bing. |

### Microsoft Clarity (10 tools)

| Tool | Description |
|---|---|
| `clarity_breakdown` | Free-form raw breakdown (1-3 dimensions). Power-user — costs 1 quota unit if not already cached. |
| `clarity_dead_clicks` | Top URLs with dead clicks (clicks on non-interactive elements — a UX problem signal). |
| `clarity_engagement` | Engagement Time + Scroll Depth per URL (or another dimension). |
| `clarity_excessive_scroll` | Top URLs with excessive scrolling (users hunting for info they can't easily find). |
| `clarity_popular_pages` | Top URLs by visits over the last days (Popular Pages metric, dimension=URL). |
| `clarity_quickback_clicks` | Top URLs with quickback clicks (user goes back immediately — page not relevant). |
| `clarity_quota_status` | Daily quota status (local counter, does not call the API). |
| `clarity_rage_clicks` | Top URLs with rage clicks (fast repeated clicks — user frustration). |
| `clarity_script_errors` | Top URLs with JS errors + error clicks (technical problems on the page). |
| `clarity_traffic` | Traffic breakdown from Microsoft Clarity (sessions, bot %, pages per session). |


## Why not the official GA4 server or mcp-gsc?

Both are good and this project doesn't pretend otherwise. Google's official [analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp) covers GA4 only; [mcp-gsc](https://github.com/AminForou/mcp-gsc) covers GSC only. If you live in one data source, use them. This project is for people who work across the whole free SEO stack and want the cross-source workflow (GSC + GA4 + Bing + Clarity) plus opinionated analysis tools in one place.

## License

MIT.

---

Built and maintained by [Raffaele Nocera](https://raffaelenocera.com) — freelance web & SEO. Available for consulting.
