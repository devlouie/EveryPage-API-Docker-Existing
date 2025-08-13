import logging
import asyncio
from typing import Dict, Any, Tuple, Optional

from openai import OpenAI
from models import AppSettings, PageProcessingStatus

logger = logging.getLogger(__name__)


def build_resetdata_messages(image_base64: str, prompt_text: str) -> list:
    return [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            {"type": "text", "text": prompt_text},
        ],
    }]


async def validate_resetdata_api_key(llm_api_key: str, config: AppSettings) -> Tuple[bool, Optional[str]]:
    """
    Performs a lightweight call to validate the provided ResetData API key.
    Returns (True, None) on success, or (False, error_message) on failure.
    """
    if not llm_api_key:
        return False, "Missing ResetData API key."

    def _run_sync() -> Tuple[bool, Optional[str]]:
        try:
            client = OpenAI(api_key=llm_api_key, base_url=str(config.resetdata_base_url))
            # Prefer a lightweight models list; if not supported, this may still 200 or 403 quickly
            _ = client.models.list()
            return True, None
        except Exception as e:
            return False, f"ResetData key validation failed: {e.__class__.__name__}: {e}"

    ok, err = await asyncio.to_thread(_run_sync)
    return ok, err

async def call_resetdata_openai_api(
    image_base64: str,
    prompt_text: str,
    config: AppSettings,
    page_number: int,
    llm_api_key: str,
    output_format: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[PageProcessingStatus], Optional[str]]:
    if not llm_api_key:
        error_msg = "Missing required ResetData LLM API key."
        logger.error(error_msg)
        return None, PageProcessingStatus.ERROR_API, error_msg

    def _run_sync() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            client = OpenAI(api_key=llm_api_key, base_url=str(config.resetdata_base_url))
            messages = build_resetdata_messages(image_base64, prompt_text)
            completion = client.chat.completions.create(
                model=config.resetdata_model,
                messages=messages,
                temperature=0.2,
                top_p=0.95,
                max_tokens=8192,
                stream=False,
            )
            content_text = completion.choices[0].message.content if completion and completion.choices else ""
            normalized = {
                "candidates": [
                    {"content": {"parts": [{"text": content_text or ""}]}}
                ]
            }
            return normalized, None
        except Exception as e:
            return None, f"ResetData API error: {e.__class__.__name__}: {e}"

    response_json, err = await asyncio.to_thread(_run_sync)
    if err:
        return None, PageProcessingStatus.ERROR_API, err
    return response_json, None, None


def parse_and_validate_ai_output(
    extracted_text: str,
    page_number: int,
    requested_format: str,
):
    if requested_format == "application/json":
        import json as _json
        try:
            clean_text = extracted_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            try:
                import html as _html
                decoded_text = _html.unescape(clean_text)
            except Exception:
                decoded_text = clean_text

            if not clean_text:
                raise _json.JSONDecodeError("Extracted text is empty.", clean_text, 0)

            parsed_json = _json.loads(decoded_text)
            logger.info(f"Successfully parsed AI response as JSON for page {page_number}.")
            return parsed_json, None, None
        except _json.JSONDecodeError as e:
            error_msg = f"Failed to parse AI response as JSON for page {page_number}: {e}."
            logger.error(error_msg)
            return extracted_text, PageProcessingStatus.ERROR_PARSING, error_msg
        except Exception as e:
            error_msg = f"Unexpected error processing AI JSON response for page {page_number}: {e}."
            logger.error(error_msg)
            return extracted_text, PageProcessingStatus.ERROR_PARSING, error_msg
    else:
        logger.info(f"Returning raw text response for page {page_number} as requested.")
        return extracted_text, None, None


