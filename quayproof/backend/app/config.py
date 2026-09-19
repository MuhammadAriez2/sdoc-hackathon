import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
except ImportError:
    pass


@dataclass
class Settings:
    provider: str = os.getenv('AI_PROVIDER', 'demo')
    storage: str = os.getenv('STORAGE_BACKEND', 'local')
    data_dir: str = os.getenv('DATA_DIR', str(ROOT / 'data'))
    token: str = os.getenv('APP_ACCESS_TOKEN', '')
    public: bool = os.getenv('PUBLIC_DEPLOYMENT', 'false').lower() == 'true'
    worker: bool = os.getenv('ENABLE_WORKER', 'true').lower() == 'true'
    gemini_key: str = os.getenv('GEMINI_API_KEY', '')
    gemini_model: str = os.getenv('GEMINI_MODEL', '')
    ollama_url: str = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    ollama_model: str = os.getenv('OLLAMA_MODEL', '')
    supabase_url: str = os.getenv('SUPABASE_URL', '').rstrip('/')
    supabase_key: str = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    bucket: str = os.getenv('SUPABASE_BUCKET', 'quayproof-documents')
    max_cases: int = int(os.getenv('MAX_CASES', '600'))
    max_pages: int = int(os.getenv('MAX_PDF_PAGES', '10'))
    ocr_language: str = os.getenv('OCR_LANGUAGE', 'eng')
    daily_limit: int = int(os.getenv('AI_DAILY_CALL_LIMIT', '100'))

    def validate(self):
        if self.provider not in {'demo', 'gemini', 'ollama'}:
            raise ValueError('AI_PROVIDER must be demo, gemini, or ollama')
        if self.storage not in {'local', 'supabase'}:
            raise ValueError('STORAGE_BACKEND must be local or supabase')
        if self.public and len(self.token) < 24:
            raise ValueError('Public deployment needs APP_ACCESS_TOKEN of at least 24 characters')
        if self.public and self.storage != 'supabase':
            raise ValueError('Public deployment requires durable Supabase storage')
        if self.storage == 'supabase' and not (self.supabase_url.startswith('https://') and self.supabase_key):
            raise ValueError('Set the Supabase HTTPS URL and server-only service-role key')


PIPELINE_VERSION = 'quayproof-1.0'
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 80000
MAX_ATTACHMENTS = 6
