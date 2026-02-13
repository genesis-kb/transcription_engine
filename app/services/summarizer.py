from app.transcript import Transcript
from app.logging import get_logger
import openai
from app.config import settings
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

logger = get_logger()

# Maximum characters per chunk for summarization
MAX_CHUNK_SIZE = 30000

class SummarizerService:
    def __init__(self, provider='openai', model='gpt-4o'):
        self.provider = provider
        self.model = model
        if self.provider == 'openai':
            self.client = openai
            self.client.api_key = settings.OPENAI_API_KEY
        elif self.provider == 'google':
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            if self.model == 'gpt-4o': # Default overwrite for google
                self.model = 'gemini-2.0-flash'
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _split_into_chunks(self, text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
        """Split text into chunks at paragraph boundaries."""
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk = current_chunk + '\n\n' + para if current_chunk else para
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def process(self, transcript: Transcript, **kwargs):
        logger.info(f"Summarizing transcript with {self.provider} (model: {self.model})...")
        text_to_summarize = transcript.outputs.get('corrected_text', transcript.outputs['raw'])
        
        text_length = len(text_to_summarize)
        logger.info(f"Text length for summarization: {text_length} characters")
        
        chunks = self._split_into_chunks(text_to_summarize)
        num_chunks = len(chunks)
        
        if num_chunks > 1:
            logger.info(f"Splitting text into {num_chunks} chunks for summarization...")
            # Summarize each chunk, then combine summaries
            chunk_summaries = []
            
            for i, chunk in enumerate(chunks, 1):
                logger.info(f"Summarizing chunk {i}/{num_chunks} ({len(chunk)} chars)...")
                summary = self._summarize_text(chunk, is_chunk=True)
                if summary:
                    chunk_summaries.append(summary)
                    logger.info(f"Chunk {i}/{num_chunks} summarization complete.")
            
            # Combine chunk summaries into final summary
            if len(chunk_summaries) > 1:
                logger.info("Combining chunk summaries into final summary...")
                combined_text = "\n\n---\n\n".join(chunk_summaries)
                final_summary = self._summarize_text(
                    combined_text, 
                    is_final=True,
                    title=transcript.source.title
                )
                transcript.summary = final_summary
            else:
                transcript.summary = chunk_summaries[0] if chunk_summaries else ""
        else:
            transcript.summary = self._summarize_text(
                text_to_summarize, 
                title=transcript.source.title
            )
        
        logger.info(f"Summarization complete. Summary length: {len(transcript.summary)} chars")

    def _summarize_text(self, text: str, is_chunk: bool = False, is_final: bool = False, title: str = None) -> str:
        """Summarize a piece of text."""
        if is_final:
            prompt = f"""The following are summaries of different parts of a transcript titled "{title}".
Please combine them into a single coherent summary that captures the key points:

{text}

Provide a well-structured summary with the main topics and key insights."""
        elif is_chunk:
            prompt = f"""Please provide a concise summary of the key points in this transcript section:

{text}

Focus on the main topics, arguments, and important details."""
        else:
            if title:
                prompt = f"""Please summarize the following transcript titled "{title}":

{text}

Provide a comprehensive summary covering the main topics, key arguments, and important insights."""
            else:
                prompt = f"""Please summarize the following text:

{text}"""
        
        try:
            if self.provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=300  # 5 minute timeout
                )
                return response.choices[0].message.content
            elif self.provider == 'google':
                model = genai.GenerativeModel(
                    self.model,
                    generation_config=GenerationConfig(
                        max_output_tokens=4096,
                    )
                )
                response = model.generate_content(
                    prompt,
                    request_options={"timeout": 300}  # 5 minute timeout
                )
                return response.text
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            return ""
