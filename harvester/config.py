"""Settings. Everything machine-specific comes from the environment or a git-ignored .env file;
no credentials are stored in the code."""
import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path=".env"):
    """Read KEY=VALUE lines from .env without overriding variables that are already set."""
    env_file = Path(path)
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    listing_url: str = "https://www.tennet.eu/de/projekte"
    base_url: str = "https://www.tennet.eu"
    source_system: str = "tennet_de_projekte"
    user_agent: str = "IRIS-SIG-27-harvester/0.1"
    contact: str = ""
    timeout_s: float = 20.0
    max_retries: int = 3
    backoff_s: float = 2.0
    default_input: Path = Path("data/raw/listing_page1.html")
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")
    gazetteer_file: Path = Path("config/gazetteer.csv")
    schema_file: Path = Path("sql/schema.sql")
    database_url: str = ""

    @property
    def full_user_agent(self):
        return f"{self.user_agent} (contact: {self.contact})" if self.contact else self.user_agent


def get_settings():
    load_dotenv()
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        contact=os.environ.get("HARVESTER_CONTACT", ""),
    )
