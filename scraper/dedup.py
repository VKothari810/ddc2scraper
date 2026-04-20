"""Deduplication logic for opportunities across sources"""
import logging
import re
from typing import Optional

from .models import Opportunity

logger = logging.getLogger(__name__)


def normalize_solicitation_number(sol_num: Optional[str]) -> Optional[str]:
    """
    Normalize solicitation number for comparison.
    Removes whitespace, hyphens, and converts to uppercase.
    """
    if not sol_num:
        return None
    normalized = re.sub(r"[\s\-_.]", "", sol_num.upper())
    return normalized if normalized else None


def generate_dedup_key(opp: Opportunity) -> str:
    """
    Generate a deduplication key for an opportunity.
    
    Priority:
    1. Normalized solicitation number (if available)
    2. Source + source_id combination
    """
    if opp.solicitation_number:
        normalized = normalize_solicitation_number(opp.solicitation_number)
        if normalized:
            return f"sol:{normalized}"
    return f"{opp.source}:{opp.source_id}"


SOURCE_PRIORITY = {
    "navy_sbir": 10,
    "erdcwerx": 9,
    "darpa": 8,
    "afwerx": 7,
    "spacewerx": 7,
    "sofwerx": 7,
    "diu": 6,
    "sam_gov": 5,
    "dsip": 4,
    "grants_gov": 3,
    "sbir_gov": 3,
    "navalx": 2,
    "army_apps_lab": 2,
}


def merge_opportunities(existing: Opportunity, new: Opportunity) -> Opportunity:
    """
    Merge two opportunities representing the same solicitation.
    Keeps the richest data from each.
    Prefers more specific/authoritative sources.
    """
    existing_priority = SOURCE_PRIORITY.get(existing.source, 0)
    new_priority = SOURCE_PRIORITY.get(new.source, 0)
    
    if new_priority > existing_priority:
        merged = new.model_copy()
        primary, secondary = new, existing
    else:
        merged = existing.model_copy()
        primary, secondary = existing, new

    if len(secondary.description) > len(primary.description):
        merged.description = secondary.description

    if secondary.posted_date and not primary.posted_date:
        merged.posted_date = secondary.posted_date

    if secondary.close_date and not primary.close_date:
        merged.close_date = secondary.close_date
    elif secondary.close_date and primary.close_date:
        merged.close_date = max(secondary.close_date, primary.close_date)

    if secondary.response_deadline and not primary.response_deadline:
        merged.response_deadline = secondary.response_deadline

    merged.naics_codes = list(set(primary.naics_codes + secondary.naics_codes))

    if not primary.agency and secondary.agency:
        merged.agency = secondary.agency
    if not primary.sub_agency and secondary.sub_agency:
        merged.sub_agency = secondary.sub_agency
    if not primary.office and secondary.office:
        merged.office = secondary.office

    if secondary.award_floor and (not primary.award_floor or secondary.award_floor > primary.award_floor):
        merged.award_floor = secondary.award_floor
    if secondary.award_ceiling and (
        not primary.award_ceiling or secondary.award_ceiling > primary.award_ceiling
    ):
        merged.award_ceiling = secondary.award_ceiling

    merged.last_updated = max(primary.last_updated, secondary.last_updated)

    if "also_found_on" not in merged.raw_data:
        merged.raw_data["also_found_on"] = []
    if secondary.source not in merged.raw_data["also_found_on"] and secondary.source != merged.source:
        merged.raw_data["also_found_on"].append(secondary.source)

    return merged


def deduplicate_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    """
    Deduplicate a list of opportunities.
    
    Returns:
        Deduplicated list with merged data where applicable
    """
    dedup_map: dict[str, Opportunity] = {}

    for opp in opportunities:
        key = generate_dedup_key(opp)

        if key in dedup_map:
            existing = dedup_map[key]
            merged = merge_opportunities(existing, opp)
            dedup_map[key] = merged
            logger.debug(f"Merged duplicate: {key} (from {opp.source} into {existing.source})")
        else:
            dedup_map[key] = opp

    result = list(dedup_map.values())
    removed_count = len(opportunities) - len(result)

    if removed_count > 0:
        logger.info(f"Deduplication removed {removed_count} duplicates, {len(result)} unique")

    return result
