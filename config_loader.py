# config_loader.py - Load application configuration from environment variables

import os
import logging
from typing import List
from models import AppSettings # Import the model from our models file
from pydantic import HttpUrl, ValidationError

logger = logging.getLogger(__name__)

def load_app_config() -> AppSettings:
    """
    Loads configuration from environment variables, validates them,
    and returns an AppSettings object.
    """
    try:
        settings = AppSettings(
            resetdata_base_url=HttpUrl(os.environ.get("LLM_BASE_URL", "https://models.au-syd.resetdata.ai/v1")),
            resetdata_model=os.environ.get("LLM_MODEL", "meta-llama/Llama-4-Maverick-17B-128E-Instruct:shared"),
            # REMOVED fixed_processing_prompt_template loading
            # Use getint helper for integer conversion with default
            max_workers=int(os.environ.get('MAX_WORKERS', '5')),
            process_timeout=int(os.environ.get('PROCESS_TIMEOUT', '90')),
            temp_dir_base=os.environ.get('TEMP_DIR_BASE', '/tmp/everypage_pure'),
            libreoffice_command=os.environ.get('LIBREOFFICE_COMMAND', 'libreoffice'),
            pdftoppm_command=os.environ.get('PDFTOPPM_COMMAND', 'pdftoppm'),
            pdfinfo_command=os.environ.get('PDFINFO_COMMAND', 'pdfinfo'),
            log_level=os.environ.get('LOG_LEVEL', 'INFO').upper()
        )

        # Basic logging after loading
        logger.info("Configuration loaded successfully.")
        # Informational logging about ResetData base URL/model
        logger.info(f"ResetData Base URL: {settings.resetdata_base_url}")
        logger.info(f"ResetData Model: {settings.resetdata_model}")
        # REMOVED logging for fixed prompt template
        logger.info(f"Max workers: {settings.max_workers}, Process timeout: {settings.process_timeout}s")
        logger.info(f"Temporary directory base: {settings.temp_dir_base}")

        return settings

    except (ValidationError, ValueError) as e:
        logger.error(f"Configuration validation failed: {e}")
        # Provide more specific error messages based on common issues
        if 'max_workers' in str(e) or 'process_timeout' in str(e):
             logger.error("Check if MAX_WORKERS and PROCESS_TIMEOUT environment variables are valid integers.")

        # Re-raise the exception to prevent the application from starting with invalid config
        raise ValueError(f"Invalid application configuration: {e}") from e

# Example usage (optional, for testing the loader directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        config = load_app_config()
        print("\nLoaded Configuration:")
        print(config.model_dump_json(indent=2))
    except ValueError as exc:
        print(f"\nFailed to load configuration: {exc}")