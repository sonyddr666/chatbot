"""Ferramenta de busca web (exemplo — usa DuckDuckGo)."""

from typing import Optional
import httpx
from urllib.parse import parse_qs, quote_plus, unquote, urlparse


def _source_url(href: str) -> str:
    """Unwrap DuckDuckGo result links so the chat can cite a useful source URL."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    redirect_url = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(redirect_url) if redirect_url else href


async def web_search(query: str, max_results: int = 3) -> Optional[str]:
    """Busca na web via DuckDuckGo (HTML scraping simplificado)."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Chatbot/1.0)"}
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Erro na busca: HTTP {resp.status_code}"

            # Parse simples de resultados
            from html.parser import HTMLParser

            class ResultParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self.in_result = False
                    self.current = {}

                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    if tag == "a" and "result__a" in attrs_dict.get("class", ""):
                        self.in_result = True
                        self.current["href"] = attrs_dict.get("href", "")

                def handle_data(self, data):
                    if self.in_result:
                        if "title" not in self.current:
                            self.current["title"] = data
                        elif "snippet" not in self.current:
                            self.current["snippet"] = data

                def handle_endtag(self, tag):
                    if tag == "a" and self.in_result:
                        self.in_result = False
                        if self.current.get("title"):
                            self.results.append(self.current)
                            self.current = {}

            parser = ResultParser()
            parser.feed(resp.text)

            if not parser.results:
                return f"Nenhum resultado encontrado para '{query}'."

            result_texts = []
            for r in parser.results[:max_results]:
                source = _source_url(r.get("href", ""))
                source_line = f"\n  Fonte: {source}" if source else ""
                result_texts.append(
                    f"- **{r.get('title', '?')}**\n"
                    f"  {r.get('snippet', '')[:200]}{source_line}"
                )

            return f"Resultados para '{query}':\n\n" + "\n\n".join(result_texts)

    except Exception as e:
        return f"Erro na busca web: {e}"


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Busca informações na web",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados (default: 3)",
                },
            },
            "required": ["query"],
        },
    },
}
