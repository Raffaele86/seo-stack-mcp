"""seo-stack-mcp — one MCP server for the whole free SEO data stack.

Sources are registered only when their credentials are configured:

- GSC + GA4 : GOOGLE_APPLICATION_CREDENTIALS or SEO_STACK_OAUTH_CLIENT
  (GA4 additionally wants GA4_PROPERTY_ID, or pass property_id per call)
- Bing      : BING_WEBMASTER_API_KEY
- Clarity   : CLARITY_API_TOKEN
"""

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .google_auth import google_configured

log = logging.getLogger("seo-stack-mcp")


def build_server() -> FastMCP:
    mcp = FastMCP("seo-stack")
    enabled = []

    if google_configured():
        from .gsc.tools import register as register_gsc
        from .ga4.tools import register as register_ga4

        register_gsc(mcp)
        enabled.append("gsc")
        register_ga4(mcp)
        enabled.append("ga4")

    if os.getenv("BING_WEBMASTER_API_KEY"):
        from .bing.tools import register as register_bing

        register_bing(mcp)
        enabled.append("bing")

    if os.getenv("CLARITY_API_TOKEN"):
        from .clarity.tools import register as register_clarity

        register_clarity(mcp)
        enabled.append("clarity")

    if not enabled:
        print(
            "seo-stack-mcp: no data source configured.\n"
            "Set at least one of:\n"
            "  GOOGLE_APPLICATION_CREDENTIALS or SEO_STACK_OAUTH_CLIENT  (GSC + GA4)\n"
            "  BING_WEBMASTER_API_KEY                                    (Bing Webmaster)\n"
            "  CLARITY_API_TOKEN                                         (Microsoft Clarity)\n"
            "See https://github.com/Raffaele86/seo-stack-mcp#quickstart",
            file=sys.stderr,
        )
        sys.exit(1)

    log.info("enabled sources: %s", ", ".join(enabled))
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    build_server().run()  # stdio transport


if __name__ == "__main__":
    main()
