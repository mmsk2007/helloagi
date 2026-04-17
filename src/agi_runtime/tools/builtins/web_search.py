"""Web search via multiple providers (Tavily, SerpAPI, DuckDuckGo)."""

import os
import json

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


def _check_web_search() -> bool:
    """At least one search provider must be available."""
    return bool(
        os.environ.get("TAVILY_API_KEY")
        or os.environ.get("SERPAPI_API_KEY")
        or True  # DuckDuckGo fallback always available
    )


@tool(
    name="web_search",
    description="Search the web for information. Uses Tavily, SerpAPI, or DuckDuckGo as fallback.",
    toolset="web",
    risk="low",
    parameters=[
        ToolParam("query", "string", "The search query"),
        ToolParam("max_results", "integer", "Maximum number of results to return", required=False, default=5),
    ],
    check_fn=_check_web_search,
)
def web_search(query: str, max_results: int = 5) -> ToolResult:
    # Try Tavily first
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        return _tavily_search(query, max_results, tavily_key)

    # Try SerpAPI
    serp_key = os.environ.get("SERPAPI_API_KEY")
    if serp_key:
        return _serpapi_search(query, max_results, serp_key)

    # Fallback to DuckDuckGo (no API key needed)
    return _duckduckgo_search(query, max_results)


def _tavily_search(query: str, max_results: int, api_key: str) -> ToolResult:
    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": max_results, "api_key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", [])[:max_results]:
            results.append(f"**{r.get('title', 'No title')}**\n{r.get('url', '')}\n{r.get('content', '')[:300]}\n")

        return ToolResult(ok=True, output="\n---\n".join(results) if results else "No results found.")
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"Tavily search failed: {e}")


def _serpapi_search(query: str, max_results: int, api_key: str) -> ToolResult:
    try:
        import requests
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": max_results, "api_key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("organic_results", [])[:max_results]:
            results.append(f"**{r.get('title', 'No title')}**\n{r.get('link', '')}\n{r.get('snippet', '')}\n")

        return ToolResult(ok=True, output="\n---\n".join(results) if results else "No results found.")
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"SerpAPI search failed: {e}")


def _duckduckgo_search(query: str, max_results: int) -> ToolResult:
    try:
        import requests
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        # Abstract
        if data.get("Abstract"):
            results.append(f"**{data.get('Heading', 'Result')}**\n{data['AbstractURL']}\n{data['Abstract']}\n")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"{topic['Text'][:300]}\n{topic.get('FirstURL', '')}\n")

        return ToolResult(ok=True, output="\n---\n".join(results) if results else f"No rich results for '{query}'. Try a more specific query.")
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"DuckDuckGo search failed: {e}")
