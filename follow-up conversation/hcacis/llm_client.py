import logging
import os
from typing import Type, TypeVar, Any, Optional
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    def __init__(self, provider: str = "gemini", model_name: str = "gemini-2.5-flash", base_url: Optional[str] = None):
        self.provider = provider.lower()
        self.model_name = model_name
        
        if self.provider == "gemini":
            self.llm = ChatGoogleGenerativeAI(model=self.model_name, temperature=0.0)
        elif self.provider == "groq":
            self.llm = ChatGroq(model=self.model_name, temperature=0.0)
        elif self.provider == "ollama":
            # Using ChatOllama requires base_url, defaults to http://localhost:11434
            url = base_url if base_url else "http://localhost:11434"
            self.llm = ChatOllama(model=self.model_name, temperature=0.0, base_url=url)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Text generation failed: {e}")
            return f"Error generating text: {e}"

    async def structured_output(self, system_prompt: str = None, user_prompt: str = None, schema: Type[T] = None, system: str = None, user: str = None) -> T:
        sys_p = system_prompt if system_prompt else system
        usr_p = user_prompt if user_prompt else user
        
        try:
            # Check if the model supports native structured output
            structured_llm = self.llm.with_structured_output(schema)
            messages = [
                SystemMessage(content=sys_p),
                HumanMessage(content=usr_p)
            ]
            result = await structured_llm.ainvoke(messages)
            return result
        except Exception as e:
            logger.warning(f"Failed to generate native structured output: {e}. Falling back to Pydantic parser.")
            try:
                # Fallback using prompt and parser if the API/Model lacks native support or fails
                parser = PydanticOutputParser(pydantic_object=schema)
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "{system_prompt}\n\n{format_instructions}"),
                    ("human", "{query}")
                ])
                chain = prompt | self.llm | parser
                return await chain.ainvoke({
                    "query": usr_p, 
                    "format_instructions": parser.get_format_instructions(),
                    "system_prompt": sys_p
                })
            except Exception as e2:
                logger.error(f"Structured output completely failed (Rate limit or API error): {e2}")
                # Return a default instance of the schema to prevent app crash
                try:
                    return schema()
                except Exception:
                    raise e2
