from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from config import get_config


class SupplementLabel(BaseModel):
    """Structured representation of a supplement label."""

    brand: str = Field(description="The brand/manufacturer name of the supplement.")
    product_name: str = Field(description="The specific product name on the label.")
    ingredients_list: List[str] = Field(
        description="List of ingredient entries exactly as they appear in the Supplement Facts."
    )
    serving_size: str = Field(
        description="Serving size text from the Supplement Facts panel (e.g. '1 tablet', '2 scoops (10 g)')."
    )
    citations_found: List[str] = Field(
        description="Any NIH, clinical trial, or scientific citations referenced near the Supplement Facts panel."
    )


def build_extraction_chain():
    """
    Build a LangChain pipeline that extracts SupplementLabel data from Markdown.
    """

    cfg = get_config()

    llm = ChatOpenAI(
        model=cfg.model_name,
        temperature=0,
        api_key=cfg.openai_api_key,
    )

    parser = PydanticOutputParser(pydantic_object=SupplementLabel)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are an expert in nutritional supplement labels. "
                    "You receive Markdown representing a web page with a Supplement Facts panel. "
                    "Extract a clean, structured representation of the label, focusing only on the "
                    "actual Supplement Facts and closely related information."
                ),
            ),
            (
                "human",
                (
                    "Extract the supplement label information from the following Markdown.\n\n"
                    "Return the result in the exact JSON schema described below.\n\n"
                    "{format_instructions}\n\n"
                    "Markdown content:\n\n"
                    "{markdown}"
                ),
            ),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    return prompt | llm | parser


def extract_supplement_label(markdown: str) -> SupplementLabel:
    """
    Run the extraction chain synchronously on provided Markdown.

    LangChain/ChatOpenAI will reason over the page content to fill the Pydantic model.
    """

    chain = build_extraction_chain()
    return chain.invoke({"markdown": markdown})


__all__ = ["SupplementLabel", "extract_supplement_label"]

