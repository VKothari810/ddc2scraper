"""Configuration and constants for the scraper"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv():
    """Load environment variables from .env file if it exists"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and value and not os.getenv(key):
                        os.environ[key] = value


_load_dotenv()


@dataclass
class Config:
    """Central configuration for the scraper"""

    # API Keys (from environment)
    sam_gov_api_key: str = field(default_factory=lambda: os.getenv("SAM_GOV_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))

    # API Endpoints
    sam_gov_api_url: str = "https://api.sam.gov/opportunities/v2/search"
    grants_gov_api_url: str = "https://api.grants.gov/v1/api/search2"
    sbir_gov_api_url: str = "https://www.sbir.gov/api/solicitations"

    # Scrape URLs
    erdcwerx_url: str = "https://www.erdcwerx.org/category/event-tech-challenges/current/"
    dsip_url: str = "https://www.dodsbirsttr.mil/topics-app/"
    diu_url: str = "https://www.diu.mil/work-with-us"
    darpa_url: str = "https://www.darpa.mil/research/opportunities"
    darpa_rss_url: str = "https://www.darpa.mil/rss/opportunities.xml"
    afwerx_url: str = "https://afwerx.com/get-funded/"
    navalx_url: str = "https://www.navytechconnect.com/"
    sofwerx_url: str = "https://sofwerx.org/"
    sofwerx_events_url: str = "https://events.sofwerx.org/"
    navy_sbir_url: str = "https://www.navysbir.com/"
    army_apps_lab_url: str = "https://www.aal.army/industry/"
    spacewerx_url: str = "https://spacewerx.us/get-funded/"

    # Rate limiting
    sam_gov_rate_limit: float = 1.0  # requests per second
    default_rate_limit: float = 2.0  # requests per second
    playwright_timeout: int = 60000  # 60 seconds

    # LLM settings
    gemini_model: str = "gemini-2.0-flash-001"
    arctic_relevance_threshold: float = 0.3
    llm_batch_size: int = 5

    # Data paths
    data_dir: str = "data"
    opportunities_file: str = "data/opportunities.json"
    arctic_opportunities_file: str = "data/arctic_opportunities.json"
    run_log_file: str = "data/run_log.json"
    debug_dir: str = "data/debug"


# Arctic keywords for pre-filtering (high confidence)
ARCTIC_KEYWORDS = [
    "arctic",
    "polar",
    "cold region",
    "cold weather",
    "extreme cold",
    "sub-arctic",
    "subarctic",
    "permafrost",
    "icebreaker",
    "high latitude",
    "alaska",
    "greenland",
    "crrel",
    "cold environment",
    "tundra",
    "glacial",
    "thermokarst",
    "boreal",
    "northern fleet",
    "cold-weather",
    "antarctic",
    "nordic",
    "scandinavia",
    "norway",
    "finland",
    "sweden",
    "iceland",
    "canada",
    "siberia",
    "barents",
    "bering",
    "beaufort",
    "chukchi",
]

# Adjacent keywords - broader scope, send to LLM for evaluation
ARCTIC_ADJACENT_KEYWORDS = [
    "extreme environment",
    "contested logistics",
    "austere environment",
    "expeditionary",
    "remote operations",
    "resilient communications",
    "indopacom",
    "eucom",
    "northcom",
    "alcom",
    "all-domain",
    "jadc2",
    "denied environment",
    "ice",
    "freeze",
    "frozen",
    "snow",
    "winter",
    "northern",
    "maritime",
    "undersea",
    "submarine",
    "climate",
    "temperature",
    "thermal",
    "insulation",
    "heating",
    "energy storage",
    "battery",
    "fuel cell",
    "renewable",
    "infrastructure",
    "runway",
    "airfield",
    "port",
    "logistics",
    "supply chain",
    "mobility",
    "vehicle",
    "sensor",
    "satellite",
    "communications",
    "radar",
    "surveillance",
    "navigation",
    "gps",
    "pnt",
    "autonomous",
    "unmanned",
    "uav",
    "usv",
    "uuv",
    "robotics",
    "ai",
    "machine learning",
    "research",
    "science",
    "geophysics",
    "oceanography",
    "meteorology",
    "weather",
    "environmental",
    "coast guard",
    "navy",
    "army",
    "air force",
    "space force",
    "marine",
    "special operations",
    "defense",
    "military",
    "dod",
    "strategic",
    "deterrence",
    "hypersonic",
    "missile",
]

# SAM.gov search keywords for arctic opportunities
SAM_SEARCH_KEYWORDS = [
    "arctic",
    "cold region",
    "polar",
    "extreme cold",
    "CRREL",
    "high latitude",
    "Alaska",
    "permafrost",
]

# SAM.gov procurement types
SAM_PROCUREMENT_TYPES = {
    "o": "Solicitation",
    "p": "Presolicitation",
    "k": "Combined Synopsis/Solicitation",
    "r": "Sources Sought",
    "s": "Special Notice",
    "a": "Award Notice",
}

# Agency filters
DOD_AGENCIES = [
    "DEPT OF DEFENSE",
    "DEPARTMENT OF DEFENSE",
    "DOD",
    "ARMY",
    "NAVY",
    "AIR FORCE",
    "DARPA",
    "DLA",
]


def get_config() -> Config:
    """Get configuration instance"""
    return Config()
