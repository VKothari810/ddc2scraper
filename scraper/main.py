"""Main orchestrator for the Arctic Defense Opportunity Scraper"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from .config import get_config
from .dedup import deduplicate_opportunities
from .llm_filter import filter_opportunities
from .models import Opportunity, RunLog

from .collectors.sam_gov import SamGovCollector
from .collectors.grants_gov import GrantsGovCollector
from .collectors.sbir_gov import SbirGovCollector
from .collectors.erdcwerx import ErdcwerxCollector
from .collectors.dsip import DsipCollector
from .collectors.diu import DiuCollector
from .collectors.darpa import DarpaCollector
from .collectors.afwerx import AfwerxCollector
from .collectors.navalx import NavalxCollector
from .collectors.sofwerx import SofwerxCollector
from .collectors.navy_sbir import NavySbirCollector
from .collectors.army_apps_lab import ArmyAppsLabCollector
from .collectors.spacewerx import SpacewerxCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ALL_COLLECTORS = [
    SamGovCollector,
    GrantsGovCollector,
    SbirGovCollector,
    ErdcwerxCollector,
    DsipCollector,
    DiuCollector,
    DarpaCollector,
    AfwerxCollector,
    NavalxCollector,
    SofwerxCollector,
    NavySbirCollector,
    ArmyAppsLabCollector,
    SpacewerxCollector,
]


def load_existing_opportunities(filepath: str) -> list[Opportunity]:
    """Load existing opportunities from JSON file"""
    path = Path(filepath)
    if not path.exists():
        return []

    try:
        with open(path) as f:
            data = json.load(f)
        return [Opportunity(**opp) for opp in data]
    except Exception as e:
        logger.error(f"Failed to load existing opportunities: {e}")
        return []


def save_opportunities(opportunities: list[Opportunity], filepath: str):
    """Save opportunities to JSON file"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = [opp.model_dump(mode="json") for opp in opportunities]

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info(f"Saved {len(opportunities)} opportunities to {filepath}")


def save_run_log(run_log: RunLog, filepath: str):
    """Save run log to JSON file"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(run_log.model_dump(mode="json"), f, indent=2, default=str)


async def run_collectors(collector_classes: list = None) -> tuple[list[Opportunity], dict]:
    """
    Run all collectors and return collected opportunities.
    
    Returns:
        Tuple of (opportunities, collector_results)
    """
    if collector_classes is None:
        collector_classes = ALL_COLLECTORS

    all_opportunities = []
    collector_results = {}

    for collector_cls in collector_classes:
        collector = collector_cls()
        result = await collector.run()

        collector_results[collector.source_name] = {
            "status": result["status"],
            "count": result["count"],
            "errors": result.get("errors", 0),
            "error_message": result.get("error_message", ""),
            "duration_seconds": result.get("duration_seconds", 0),
        }

        if result["status"] == "success":
            all_opportunities.extend(result["opportunities"])

    return all_opportunities, collector_results


async def main():
    """Main entry point for the scraper"""
    config = get_config()
    run_log = RunLog()

    logger.info("=" * 60)
    logger.info("Starting Arctic Defense Opportunity Scraper")
    logger.info("=" * 60)

    existing = load_existing_opportunities(config.opportunities_file)
    logger.info(f"Loaded {len(existing)} existing opportunities")

    logger.info("Running all collectors...")
    new_opportunities, collector_results = await run_collectors()
    run_log.collector_results = collector_results
    run_log.collectors_run = list(collector_results.keys())

    for source, result in collector_results.items():
        status_emoji = "✓" if result["status"] == "success" else "✗"
        logger.info(f"  {status_emoji} {source}: {result['count']} opportunities")
        if result.get("error_message"):
            run_log.errors.append(f"{source}: {result['error_message']}")

    logger.info(f"Collected {len(new_opportunities)} new opportunities")

    all_opportunities = existing + new_opportunities
    logger.info(f"Total before dedup: {len(all_opportunities)}")

    deduped = deduplicate_opportunities(all_opportunities)
    logger.info(f"After deduplication: {len(deduped)}")

    logger.info("Running LLM filter for arctic relevance...")
    all_scored, arctic_relevant = await filter_opportunities(deduped)

    run_log.total_opportunities = len(all_scored)
    run_log.arctic_opportunities = len(arctic_relevant)
    run_log.completed_at = datetime.utcnow()

    save_opportunities(all_scored, config.opportunities_file)
    save_opportunities(arctic_relevant, config.arctic_opportunities_file)
    save_run_log(run_log, config.run_log_file)

    logger.info("=" * 60)
    logger.info("Scraper run complete!")
    logger.info(f"  Total opportunities: {len(all_scored)}")
    logger.info(f"  Arctic-relevant: {len(arctic_relevant)}")
    logger.info(f"  Errors: {len(run_log.errors)}")
    logger.info("=" * 60)

    return run_log


if __name__ == "__main__":
    asyncio.run(main())
