import logging
from langchain_community.tools import DuckDuckGoSearchRun

logger = logging.getLogger(__name__)

class WebEngine:
    def __init__(self):
        try:
            self.search_tool = DuckDuckGoSearchRun()
        except Exception as e:
            logger.error(f"Failed to initialize DuckDuckGoSearchRun: {e}")
            self.search_tool = None

    def search(self, query: str) -> str:
        if not self.search_tool:
            return "Web search engine is not initialized."
        try:
            result = self.search_tool.invoke(query)
            return result
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return f"Web search failed: {e}"
