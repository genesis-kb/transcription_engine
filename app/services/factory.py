import importlib
import inspect
import pkgutil
from typing import Dict, Any

from app.data_writer import DataWriter
from app.logging import get_logger
from app.services.providers.base import BaseTranscriptionService

logger = get_logger()

_REGISTRY: Dict[str, type[BaseTranscriptionService]] = {}


def discover_providers():
    """Automatically discover all ASR providers in the providers directory."""
    import app.services.providers as providers

    for _, module_name, _ in pkgutil.iter_modules(providers.__path__):
        if module_name == "base":
            continue

        try:
            module = importlib.import_module(f"app.services.providers.{module_name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseTranscriptionService) and obj is not BaseTranscriptionService:
                    provider_name = getattr(obj, "PROVIDER_NAME", module_name.lower())
                    _REGISTRY[provider_name] = obj
        except ImportError as e:
            logger.warning(f"Could not load provider module '{module_name}': {e}")
        except Exception as e:
            logger.error(f"Error loading provider module '{module_name}': {e}")


def get_asr_service(provider: str, config: dict, metadata_writer: DataWriter) -> BaseTranscriptionService:
    """Retrieve the instantiated ASR service for the given provider."""
    if not _REGISTRY:
        discover_providers()

    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown ASR provider: '{provider}'. Choose from {list(_REGISTRY.keys())}"
        )
    return cls.from_config(config, metadata_writer)
