import importlib
import inspect
import pkgutil
from typing import Dict

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
                    if getattr(obj, "__module__", None) != module.__name__:
                        continue
                    
                    provider_name = getattr(obj, "PROVIDER_NAME", module_name.lower())
                    if provider_name in _REGISTRY and _REGISTRY[provider_name] is not obj:
                        existing = _REGISTRY[provider_name]
                        raise ValueError(
                            f"Provider name collision during registration: "
                            f"'{provider_name}' is already registered to "
                            f"{existing.__module__}.{existing.__name__}. "
                            f"Cannot register {obj.__module__}.{obj.__name__}."
                        )
                    _REGISTRY[provider_name] = obj
        except ImportError as e:
            logger.warning(f"Could not load provider module '{module_name}': {e}")
        except ValueError:
            _REGISTRY.clear()
            raise
        except Exception as e:
            logger.error(f"Error loading provider module '{module_name}': {e}")


def reset_registry():
    """Clear the provider registry (primarily for testing)."""
    _REGISTRY.clear()


def get_available_providers() -> list[str]:
    """Return a list of discovered provider names."""
    if not _REGISTRY:
        discover_providers()
    return list(_REGISTRY.keys())


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
