# main_api.py - FastAPI application entry point for EveryPage Pure

import logging
import os
import time # <-- ADDED IMPORT
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import (
    FastAPI, File, UploadFile, Depends, HTTPException, status, BackgroundTasks, Request, Form
)
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import modules created in previous steps
from config_loader import load_app_config
from models import (
    AppSettings, HealthCheckResponse, AggregatedResult
)
from workflow_orchestrator import process_document_stateless
from external_commands import check_command_availability
from resetdata_ai_adapter import validate_resetdata_api_key

# --- Configuration Loading & Basic Setup ---

try:
    config: AppSettings = load_app_config()
except ValueError as e:
    # Configuration failed validation, critical error
    logging.basicConfig(level="ERROR", format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.critical(f"CRITICAL ERROR: Failed to load application configuration. Exiting. Error: {e}")
    # In a real deployment, you might exit or raise a more specific startup exception
    # For simplicity here, we'll let it potentially crash later if config is accessed.
    # Or raise SystemExit(1) # Uncomment to force exit on config error
    raise SystemExit(f"Configuration Error: {e}")


# --- Logging Setup ---
# Configure logging AFTER loading config, using the specified level
log_level = config.log_level.upper()
numeric_level = getattr(logging, log_level, logging.INFO) # Default to INFO if invalid level
logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.info(f"Logging configured at level: {log_level}")


# --- Global Objects ---
# Stateless API: no job store

# Create the FastAPI app instance
app = FastAPI(
    title="EveryPage Pure API",
    description="Processes documents page-by-page using ResetData's OpenAI-compatible Vision API.",
    version="1.0.0", # Consider making this dynamic
    # Add OpenAPI tags if desired for better docs organization
)

# --- CORS Middleware ---
# Allow all origins for simplicity in this example. Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify origins like ["http://localhost:8000", "http://127.0.0.1:8000"]
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# --- ResetData Key Validation Dependency ---
async def require_resetdata_key(request: Request) -> str:
    """Extracts and validates the user's ResetData API key by calling ResetData once."""
    key = request.headers.get("x-resetdata-key") or request.query_params.get("resetdata_key")
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing ResetData API key. Provide in header 'x-resetdata-key' or query 'resetdata_key'.")
    ok, err = await validate_resetdata_api_key(key, config)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err or "Invalid ResetData API key.")
    return key


# --- Static Files Mounting (for Web UI) ---
# This will be done *after* API routes are defined below to avoid conflicts

# --- Event Handlers (Startup/Shutdown) ---

@app.on_event("startup")
async def startup_event():
    """Tasks to perform when the application starts."""
    logger.info("Application startup initiated.")
    # Ensure base temporary directory exists
    base_temp_dir = Path(config.temp_dir_base)
    try:
        base_temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Base temporary directory ensured: {base_temp_dir}")
    except OSError as e:
        logger.error(f"Failed to create base temporary directory '{base_temp_dir}': {e}. Processing might fail.")
        # Depending on severity, you might want to prevent startup

    # Check for external command availability (optional, provides early feedback)
    check_command_availability(config.libreoffice_command)
    check_command_availability(config.pdftoppm_command)
    check_command_availability(config.pdfinfo_command)

    logger.info("Application startup complete.")


# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root():
    """Serves the main web interface HTML file."""
    ui_path = Path("web_interface.html")
    if ui_path.is_file():
        return FileResponse(ui_path)
    else:
        # Fallback if the HTML file is missing
        logger.warning("web_interface.html not found. Serving basic message.")
        return HTMLResponse("<html><body><h1>EveryPage Pure API</h1><p>Web interface file not found.</p></body></html>")

# REMOVED the problematic /{filename:path} route


@app.get("/health", response_model=HealthCheckResponse, tags=["Status"])
async def health_check(resetdata_key: str = Depends(require_resetdata_key)):
    """Performs a health check of the API and its dependencies."""
    logger.info(f"Health check requested (ResetData Key ending '...{resetdata_key[-4:]}').")
    dependencies_status = {
        "libreoffice": "available" if check_command_availability(config.libreoffice_command) else "missing",
        "pdftoppm": "available" if check_command_availability(config.pdftoppm_command) else "missing",
        "pdfinfo": "available" if check_command_availability(config.pdfinfo_command) else "missing",
    }
    overall_status = "healthy"
    if "missing" in dependencies_status.values():
        overall_status = "degraded" # Indicate potential issues

    # Using per-request API key for ResetData; report mode accordingly
    llm_status = "per_request"
    active_jobs = 0

    return HealthCheckResponse(
        status=overall_status,
        active_jobs_count=active_jobs,
        dependencies=dependencies_status,
        llm_status=llm_status
    )

@app.post("/scan", response_model=AggregatedResult, tags=["Processing"])
async def scan_document(
    file: UploadFile = File(..., description="The document file to process (e.g., PDF, DOCX, ODT)."),
    user_prompt: str = Form(..., description="The user-defined prompt to use for processing."),
    output_format: str = Form("json", description="Desired output format ('json' or 'text')."),
    use_meta_intelligence: str = Form("false", description="Whether to enable two-pass meta intelligence ('true' or 'false')."),
    resetdata_key: str = Depends(require_resetdata_key)
):
    """
    Accepts a document file and returns the final aggregated results synchronously (stateless).
    """
    logger.info(f"Scan request received for file '{file.filename}' (Size: {file.size}, Type: {file.content_type}). ResetData Key: ...{resetdata_key[-4:]}. Prompt: '{user_prompt[:100]}...'")

    # Create a request-scoped directory within the base temp directory
    req_id = f"req_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    job_dir = Path(config.temp_dir_base) / req_id
    upload_dir = job_dir / "upload"
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created job directory: {job_dir}")
    except OSError as e:
        logger.error(f"Failed to create job directory '{job_dir}': {e}")
        raise HTTPException(status_code=500, detail="Failed to create temporary directory for processing.")

    # Sanitize filename (optional, but good practice)
    # Simple sanitization: replace spaces, remove unsafe chars. Improve as needed.
    safe_filename = "".join(c if c.isalnum() or c in ['.', '-', '_'] else '_' for c in file.filename)
    if not safe_filename: safe_filename = "uploaded_file" # Fallback
    input_file_path = upload_dir / safe_filename

    # Save the uploaded file
    try:
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved uploaded file to: {input_file_path}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file '{input_file_path}': {e}", exc_info=True)
        # Clean up job directory if save fails
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Could not save uploaded file: {e}")
    finally:
        # Ensure the file pointer is closed
        await file.close()


    # Process synchronously (stateless) and return final result
    try:
        result = await process_document_stateless(
            input_file_path=input_file_path,
            user_prompt=user_prompt,
            output_format=output_format,
            use_meta_intelligence=(use_meta_intelligence.lower() == 'true'),
            config=config,
            llm_api_key=resetdata_key,
            job_dir=job_dir,
        )
        return result
    except Exception as e:
        logger.error(f"Stateless processing failed: {e}", exc_info=True)
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


# Removed /jobs/* endpoints for stateless design


# --- Mount Static Files (AFTER API routes) ---
# Serve files from the current directory (".")
# html=True allows serving index.html for the root path of the mount
# Check_dir=False prevents startup error if dir doesn't exist (though "." always exists)
app.mount("/", StaticFiles(directory=".", html=True, check_dir=False), name="static")

# --- Main Execution Guard ---
# Allows running directly with uvicorn for development:
# uvicorn main_api:app --reload
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn development server...")
    # Use host 0.0.0.0 to be accessible externally (e.g., within Docker)
    # Use port 8000 by default
    uvicorn.run(
        "main_api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)), # Allow port override via env var
        reload=True, # Enable auto-reload for development
        log_level=config.log_level.lower() # Pass log level to uvicorn
    )