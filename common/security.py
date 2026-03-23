import os
import yaml
from pathlib import Path
from typing import List, Optional

class Vault:
    """
    Handles security and path validation for the AutoWSL-Bridge.
    Ensures that only whitelisted Windows directories are accessible from WSL.
    """
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initializes the Vault by loading configuration settings.
        :param config_path: Path to the YAML configuration file relative to the project root.
        """
        # Resolve config relative to the project root to ensure it's found regardless of where the script is run
        root_dir = Path(__file__).resolve().parent.parent
        self.config_path = root_dir / config_path
        self.allowed_paths = self._load_allowed_paths()

    def _load_allowed_paths(self) -> List[Path]:
        """
        Loads the list of whitelisted Windows paths from the configuration file.
        :return: A list of resolved Path objects representing allowed directories.
        """
        if not self.config_path.exists():
            return []
        
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            # Resolve each path to its absolute form for secure comparison
            return [Path(p).resolve() for p in config.get("vault", [])]
        except Exception:
            return []

    def is_safe(self, target_path: str) -> bool:
        """
        Checks if a requested Windows path is within the whitelisted folders.
        :param target_path: The path string to validate.
        :return: True if the path is inside an allowed directory, False otherwise.
        """
        try:
            target = Path(target_path).resolve()
            for allowed in self.allowed_paths:
                # Check if the target is the allowed path itself or a child of it
                if target == allowed or allowed in target.parents:
                    return True
        except Exception:
            return False
        return False

    def get_token(self) -> str:
        """
        Retrieves the security token from the configuration.
        :return: The token string, or an empty string if not found or on error.
        """
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            return config.get("security", {}).get("token", "")
        except Exception:
            return ""

    def verify_token(self, token: str) -> bool:
        """
        Compares a provided token against the one stored in the configuration.
        :param token: The token string to verify.
        :return: True if the tokens match and are not empty, False otherwise.
        """
        expected = self.get_token()
        return token == expected and expected != ""

    def is_read_only(self) -> bool:
        """
        Checks if the bridge is currently in read-only mode.
        :return: True if read-only is enabled or on configuration error, False otherwise.
        """
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            return config.get("security", {}).get("read_only", False)
        except Exception:
            # Default to read-only (safe mode) if configuration cannot be read
            return True
