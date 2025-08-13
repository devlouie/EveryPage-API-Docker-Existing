## EveryPage (ResetData Edition)

Process documents and images page-by-page using ResetData’s OpenAI‑compatible Vision API. Bring your own ResetData key per request. Simple UI included.

### What it does
- Accepts PDFs, Office docs (via LibreOffice), and images
- Screenshots each page and sends to ResetData with your instructions
- Returns JSON or plain text per page and an easy summary
- Optional “Meta Intelligence” pass over the first few pages for better context

### Requirements
- Docker (recommended) or Python 3.9+
- The container installs LibreOffice and Poppler for conversion/screenshotting
- Your ResetData API key (sent per request; not stored on server)

### Quick start (Docker)
```bash
docker build -t everypage:latest .
docker run -p 8001:8001 everypage:latest
```
Open http://localhost:8001, paste your ResetData key, upload a file, pick JSON or Text, and run.

### Quick start (Portainer)
Two clean options:
1) Repository build (Portainer builds from your Git repo)
   - Stacks > Add stack > Repository
   - Repo URL: your GitHub repo; Compose path: docker-compose.yml
   - Deploy

2) Upload compose (requires a prebuilt image)
   - Build and push an image:
     ```bash
     docker build -t YOURUSER/everypage:latest .
     docker login && docker push YOURUSER/everypage:latest
     ```
   - Stacks > Add stack > Upload > Use this compose:
     ```yaml
     services:
       everypage:
         image: YOURUSER/everypage:latest
         ports:
           - "8001:8001"
         environment:
           - LOG_LEVEL=INFO
           - MAX_WORKERS=5
           - PROCESS_TIMEOUT=60
         volumes:
           - everypage_data:/app/output
         restart: unless-stopped
     volumes:
       everypage_data:
     ```

### Minimal configuration
- Key is provided per request: header `x-resetdata-key: YOUR_KEY` or query `?resetdata_key=YOUR_KEY`
- Optional envs (defaults are sensible):
  - `LOG_LEVEL` (INFO), `MAX_WORKERS` (5), `PROCESS_TIMEOUT` (90)
  - `LLM_BASE_URL` (ResetData base URL), `LLM_MODEL` (model name)

### Health check
`/health` requires the ResetData key (same as other endpoints). If you need unauthenticated health, add a separate endpoint like `/ping` and a compose healthcheck. By default we ship without a healthcheck so stacks don’t fail.

### API cheatsheet
- GET `/health`
  - Example: `curl -H "x-resetdata-key: YOUR_KEY" http://localhost:8001/health`
- POST `/scan` (multipart/form-data)
  - Fields: `file` (required), `user_prompt` (required), `output_format` (json|text), `use_meta_intelligence` (true|false)
  - Example:
    ```bash
    curl -X POST http://localhost:8001/scan \
      -H "x-resetdata-key: YOUR_KEY" \
      -F "file=@/path/to/doc.pdf" \
      -F "user_prompt=Summarize key points as JSON" \
      -F "output_format=json" \
      -F "use_meta_intelligence=false"
    ```

### Notes
- First build can take a while (LibreOffice/Poppler layers)
- Model parameters and provider base URL are configurable via envs
- No server‑side API keys; you control the key per call

### License
MIT
