"""
ParameterStore - Runtime parameter management from database.
Provides dynamic configuration that can be updated from the dashboard.
"""

import time
from typing import Optional
from db import get_all_parameters, get_parameter, init_parameters, DEFAULT_DB_PATH
from logger import get_logger

logger = get_logger(__name__)


class ParameterStore:
    """
    Manages runtime parameters loaded from the database.
    Supports periodic reloading and fallback to cached values.
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH, reload_interval: int = 30):
        self.db_path = db_path
        self.reload_interval = reload_interval
        self._params: dict[str, float] = {}
        self._last_reload: float = 0.0
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize parameters table and load initial values."""
        try:
            init_parameters(self.db_path)
            self.reload_params()
            self._initialized = True
            logger.info(f"ParameterStore initialized with {len(self._params)} parameters")
        except Exception as e:
            logger.error(f"Failed to initialize ParameterStore: {e}")
    
    def reload_params(self) -> bool:
        """Reload all parameters from the database."""
        try:
            params = get_all_parameters(self.db_path)
            if params:
                self._params = {p["name"]: p["value"] for p in params}
                self._last_reload = time.time()
                logger.debug(f"Reloaded {len(self._params)} parameters from database")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reload parameters: {e}")
            return False
    
    def maybe_reload(self) -> None:
        """Reload parameters if enough time has passed since last reload."""
        if time.time() - self._last_reload >= self.reload_interval:
            self.reload_params()
    
    def get_param(self, name: str, default: Optional[float] = None) -> float:
        """
        Get a parameter value.
        Falls back to default if parameter not found.
        """
        if name in self._params:
            return self._params[name]
        
        if default is not None:
            return default
        
        param = get_parameter(name, self.db_path)
        if param:
            self._params[name] = param["value"]
            return param["value"]
        
        logger.warning(f"Parameter {name} not found, no default provided")
        return 0.0
    
    def get_all(self) -> dict[str, float]:
        """Get all cached parameters."""
        return self._params.copy()
    
    def get_last_reload_time(self) -> float:
        """Get timestamp of last successful reload."""
        return self._last_reload
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


_store: Optional[ParameterStore] = None


def get_store(db_path: str = DEFAULT_DB_PATH) -> ParameterStore:
    """Get or create the global ParameterStore instance."""
    global _store
    if _store is None:
        _store = ParameterStore(db_path)
        _store.initialize()
    return _store


def get_param(name: str, default: Optional[float] = None) -> float:
    """Convenience function to get a parameter value."""
    return get_store().get_param(name, default)


def reload_params() -> bool:
    """Convenience function to reload all parameters."""
    return get_store().reload_params()


def maybe_reload_params() -> None:
    """Convenience function to reload if interval has passed."""
    get_store().maybe_reload()
