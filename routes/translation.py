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

translation_queue = []
translation_in_progress = False

@router.post("/add_to_queue/")
async def add_to_queue(
    target_lang: str = Form("hi-IN"),
    output_dir: str = Form("output/"),
    source_file: Optional[UploadFile] = File(None),
):
    temp_file_path = None
    try:
        if source_file:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                shutil.copyfileobj(source_file.file, tmp)
                temp_file_path = tmp.name
                
            with open(temp_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                
            filename = source_file.filename
            
            translation_queue.append({
                "filename": filename,
                "text": text,
                "target_lang": target_lang,
                "output_dir": output_dir
            })
        else:
            raise ValueError("No source_file provided.")

        return {
            "status": "queued",
            "message": f"Translation source {filename} has been added to the queue.",
        }
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
                logger.info(f"Processing translation job for {job['filename']}")
                
                pipeline = TranslationPipeline(
                    registry_path=settings.GENESIS_KB_REGISTRY_PATH,
                    sarvam_api_key=settings.SARVAM_API_KEY,
                    target_lang=job['target_lang'],
                    gemma_model=settings.GEMMA_MODEL
                )
                
                result = pipeline.translate_text(job['text'])
                
                os.makedirs(job['output_dir'], exist_ok=True)
                base, _ = os.path.splitext(job['filename'])
                output_path = os.path.join(job['output_dir'], f"{base}_{job['target_lang']}.md")
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result.translated_text)
                
                logger.info(f"Translated text saved to {output_path}")
                
        except Exception as e:
            logger.error(f"Translation pipeline failed: {e}")
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
