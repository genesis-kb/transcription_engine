import os
import shutil
import tempfile
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from app.logging import get_logger
from app.config import settings
from app.services.translation.pipeline import TranslationPipeline

logger = get_logger()
router = APIRouter(tags=["Translation"])

BASE_OUTPUT_DIR = os.path.abspath("output")
MAX_QUEUE_SIZE = 100
translation_queue = []
translation_in_progress = False

def validate_and_get_output_path(output_dir: str, filename: str, target_lang: str, output_filename: Optional[str] = None) -> str:
    if output_filename:
        sanitized_filename = os.path.normpath(output_filename)
        if os.path.isabs(sanitized_filename):
            sanitized_filename = sanitized_filename.lstrip("/")
            drive, tail = os.path.splitdrive(sanitized_filename)
            sanitized_filename = tail.lstrip("/")
        resolved_path = os.path.abspath(os.path.join(BASE_OUTPUT_DIR, sanitized_filename))
    else:
        safe_filename = os.path.basename(filename)
        base, _ = os.path.splitext(safe_filename)
        out_file = f"{base}_{target_lang}.md"
        
        sanitized_dir = os.path.normpath(output_dir)
        if os.path.isabs(sanitized_dir):
            sanitized_dir = sanitized_dir.lstrip("/")
            drive, tail = os.path.splitdrive(sanitized_dir)
            sanitized_dir = tail.lstrip("/")
        resolved_dir = os.path.abspath(os.path.join(BASE_OUTPUT_DIR, sanitized_dir))
        if not resolved_dir.startswith(BASE_OUTPUT_DIR):
            raise ValueError("Directory traversal attempt detected")
        resolved_path = os.path.abspath(os.path.join(resolved_dir, out_file))
        
    if not resolved_path.startswith(BASE_OUTPUT_DIR):
        raise ValueError("Directory traversal attempt detected")
        
    return resolved_path

@router.post("/add_to_queue/")
async def add_to_queue(
    target_lang: str = Form("hi-IN"),
    output_dir: str = Form("output/"),
    output_filename: Optional[str] = Form(None),
    registry: Optional[str] = Form(None),
    log_dir: Optional[str] = Form(None),
    debug: Optional[bool] = Form(None),
    source_file: Optional[UploadFile] = File(None),
):
    if source_file is None:
        raise HTTPException(status_code=400, detail="source_file is required")

    if len(translation_queue) >= MAX_QUEUE_SIZE:
        raise HTTPException(status_code=429, detail="Translation queue is full. Please try again later.")

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            shutil.copyfileobj(source_file.file, tmp)
            temp_file_path = tmp.name
            
        file_size = os.path.getsize(temp_file_path)
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds the 10MB limit.")

        try:
            with open(temp_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file encoding. Only UTF-8 text files are supported: {e}"
            )
            
        filename = os.path.basename(source_file.filename) if source_file.filename else "source.txt"
        
        try:
            _ = validate_and_get_output_path(output_dir, filename, target_lang, output_filename)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
        translation_queue.append({
            "filename": filename,
            "text": text,
            "target_lang": target_lang,
            "output_dir": output_dir,
            "output_filename": output_filename,
            "registry": registry,
            "log_dir": log_dir,
            "debug": debug
        })

        return {
            "status": "queued",
            "message": f"Translation source {filename} has been added to the queue.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@router.post("/start/")
async def start(background_tasks: BackgroundTasks):
    global translation_in_progress

    if not translation_queue:
        return {
            "status": "empty",
            "message": "No items in the translation queue.",
        }

    if translation_in_progress:
        return {
            "status": "in_progress",
            "message": "Translation process is already running.",
        }

    translation_in_progress = True

    def run_translation_queue():
        global translation_in_progress
        try:
            while translation_queue:
                job = translation_queue.pop(0)
                try:
                    logger.info(f"Processing translation job for {job['filename']}")
                    
                    registry_path = job.get('registry') or settings.GENESIS_KB_REGISTRY_PATH
                    debug_val = job.get('debug') or False
                    
                    pipeline = TranslationPipeline(
                        registry_path=registry_path,
                        sarvam_api_key=settings.SARVAM_API_KEY,
                        target_lang=job['target_lang'],
                        gemma_model=settings.GEMMA_MODEL,
                        debug=debug_val
                    )
                    
                    result = pipeline.translate_text(job['text'])
                    
                    output_path = validate_and_get_output_path(
                        job['output_dir'],
                        job['filename'],
                        job['target_lang'],
                        job.get('output_filename')
                    )
                    resolved_dir = os.path.dirname(output_path)
                    os.makedirs(resolved_dir, exist_ok=True)
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(result.translated_text)
                    
                    logger.info(f"Translated text saved to {output_path}")
                except Exception as e:
                    logger.error(
                        f"Translation job failed for filename={job.get('filename')}, "
                        f"target_lang={job.get('target_lang')}: {e}"
                    )
        finally:
            translation_in_progress = False

    background_tasks.add_task(run_translation_queue)

    return {
        "status": "started",
        "message": "Translation process has started in the background.",
    }

@router.get("/queue/")
async def get_queue():
    return {"data": [{"filename": job["filename"], "status": "queued"} for job in translation_queue]}
