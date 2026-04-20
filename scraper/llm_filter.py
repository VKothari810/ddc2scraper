"""Arctic defense relevance filtering - keyword and rule-based scoring"""
import logging
import re
from typing import Optional

from .config import get_config
from .models import Opportunity

logger = logging.getLogger(__name__)

# Defense-related sources that should get higher baseline scores
DEFENSE_SOURCES = {
    "sam_gov", "dsip", "darpa", "diu", "afwerx", "spacewerx", 
    "sofwerx", "navy_sbir", "navalx", "army_apps_lab", "erdcwerx"
}

# Keywords that indicate DEFENSE + ARCTIC relevance (high confidence)
ARCTIC_DEFENSE_KEYWORDS = [
    # Arctic/cold specific military terms
    "arctic operations",
    "arctic warfare",
    "cold weather operations", 
    "cold region operations",
    "extreme cold operations",
    "polar operations",
    "high latitude operations",
    "northern operations",
    "cold weather military",
    "arctic defense",
    "polar defense",
    
    # Military cold-region infrastructure
    "crrel",  # Cold Regions Research and Engineering Laboratory
    "cold regions research",
    "icebreaker",
    "ice operations",
    "permafrost infrastructure",
    "arctic base",
    "arctic airfield",
    "cold weather equipment",
    "cold weather gear",
    "extreme cold environment",
    
    # Geographic military relevance
    "alaskan command",
    "alcom",
    "joint base elmendorf",
    "fort wainwright", 
    "eielson",
    "thule",
    "northern command",
    "northcom arctic",
    
    # Specific defense arctic programs
    "arctic strategy",
    "arctic domain awareness",
    "polar security",
    "northern flank",
    "arctic undersea",
    "ice navigation",
    "polar navigation",
]

# Keywords that suggest arctic relevance but need defense context
# Note: These must be whole words or specific phrases to avoid false matches
ARCTIC_CONTEXT_KEYWORDS = [
    "arctic",
    "polar",
    "subarctic", 
    "sub-arctic",
    "tundra",
    "permafrost",
    "glacial",
    "sea ice",
    "ice operations",
    "icebreaking",
    "frozen terrain",
    "extreme cold",
    "cold region",
    "cold weather",
    "high latitude",
    "northern theater",
    "greenland",
    "nordic",
    "antarctic",
    "winter warfare",
    "snow operations",
    "thermal management",
    "cold start",
    "freeze protection",
    "low temperature",
    "extreme environment",
    "harsh environment",
    "austere environment",
]

# Keywords that indicate defense/military context
DEFENSE_CONTEXT_KEYWORDS = [
    "dod", "department of defense", "defense", "military",
    "army", "navy", "air force", "marine", "space force", "coast guard",
    "darpa", "diu", "afwerx", "sofwerx", "spacewerx", "erdcwerx", "navalx",
    "sbir", "sttr", "baa", "broad agency announcement",
    "solicitation", "contract", "procurement",
    "warfighter", "combat", "tactical", "strategic", "operational",
    "weapon", "munition", "platform", "system",
    "c4isr", "isr", "surveillance", "reconnaissance",
    "logistics", "sustainment", "mobility",
    "sensor", "radar", "sonar", "communications",
    "autonomous", "unmanned", "uav", "usv", "uuv",
    "hypersonic", "missile", "deterrence",
]

# Exclusion patterns - these indicate NON-defense opportunities
EXCLUSION_PATTERNS = [
    r"alaska native",
    r"native american",
    r"indigenous",
    r"tribal",
    r"indian health",
    r"cultural heritage",
    r"historical preservation",
    r"fish and wildlife",
    r"national park",
    r"forest service",
    r"bureau of land management",
    r"environmental protection agency",
    r"education grant",
    r"scholarship",
    r"fellowship",
    r"doctoral dissertation",
    r"academic research",
    r"university grant",
    r"social science",
    r"anthropology",
    r"archaeology",
    r"community development",
    r"economic development",
    r"housing",
    r"healthcare",
    r"public health",
    r"mental health",
    r"substance abuse",
    r"agriculture",
    r"farming",
    r"fisheries management",
    r"wildlife conservation",
    r"endangered species",
    r"climate change adaptation",  # civilian context
    r"renewable energy.*community",
    r"rural development",
]


def is_defense_opportunity(opp: Opportunity) -> bool:
    """Check if opportunity is from a defense source or has defense context"""
    # Check source
    if opp.source in DEFENSE_SOURCES:
        return True
    
    # Check agency
    agency_text = f"{opp.agency or ''} {opp.sub_agency or ''} {opp.office or ''}".lower()
    defense_agencies = ["dod", "defense", "army", "navy", "air force", "darpa", "dla", "disa"]
    if any(da in agency_text for da in defense_agencies):
        return True
    
    # Check title/description for defense context
    text = f"{opp.title} {opp.description}".lower()
    defense_hits = sum(1 for kw in DEFENSE_CONTEXT_KEYWORDS if kw in text)
    
    return defense_hits >= 2


def should_exclude(opp: Opportunity) -> bool:
    """Check if opportunity should be excluded (non-defense)"""
    text = f"{opp.title} {opp.description} {opp.agency or ''}".lower()
    
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, text):
            return True
    
    return False


def score_opportunity(opp: Opportunity) -> tuple[float, str, list[str]]:
    """
    Score an opportunity for arctic defense relevance.
    
    Returns:
        Tuple of (score, reasoning, keywords_found)
    """
    text = f"{opp.title} {opp.description}".lower()
    agency_text = f"{opp.agency or ''} {opp.sub_agency or ''} {opp.office or ''}".lower()
    full_text = f"{text} {agency_text}"
    
    keywords_found = []
    
    # Check exclusions first
    if should_exclude(opp):
        return 0.0, "Excluded: Non-defense opportunity (social services, education, wildlife, etc.)", []
    
    # Check for high-confidence arctic defense keywords
    for kw in ARCTIC_DEFENSE_KEYWORDS:
        if kw in full_text:
            keywords_found.append(kw)
    
    if keywords_found:
        score = min(1.0, 0.8 + len(keywords_found) * 0.05)
        return score, f"High arctic defense relevance: {', '.join(keywords_found[:3])}", keywords_found
    
    # Check for arctic context keywords
    arctic_keywords = []
    for kw in ARCTIC_CONTEXT_KEYWORDS:
        if kw in full_text:
            arctic_keywords.append(kw)
    
    # Must have defense context for arctic keywords to count
    is_defense = is_defense_opportunity(opp)
    
    if arctic_keywords and is_defense:
        # Has arctic keywords AND defense context
        score = min(0.7, 0.4 + len(arctic_keywords) * 0.1)
        keywords_found = arctic_keywords
        return score, f"Arctic keywords with defense context: {', '.join(arctic_keywords[:3])}", keywords_found
    
    if arctic_keywords and not is_defense:
        # Arctic keywords but no defense context - low score
        return 0.1, f"Arctic keywords but non-defense context", arctic_keywords
    
    # Defense opportunity without arctic keywords
    if is_defense:
        # Check for technologies highly applicable to arctic operations
        high_relevance_tech = [
            "undersea", "submarine", "sonar", "maritime domain", "naval",
            "expeditionary", "contested logistics", "forward operating",
            "remote operations", "denied environment", "resilient",
            "all-weather", "rugged", "ruggedized"
        ]
        high_tech_found = [kw for kw in high_relevance_tech if kw in full_text]
        
        if high_tech_found:
            return 0.35, f"Defense technology relevant to arctic operations: {', '.join(high_tech_found[:3])}", high_tech_found
        
        # General defense tech with potential arctic application
        tech_keywords = ["sensor", "autonomous", "unmanned", "communications", "logistics", 
                        "thermal", "battery", "energy storage", "propulsion"]
        tech_found = [kw for kw in tech_keywords if kw in full_text]
        
        if tech_found:
            return 0.2, f"Defense technology potentially applicable to arctic: {', '.join(tech_found[:3])}", tech_found
        
        return 0.1, "Defense opportunity - potential arctic application", []
    
    # Non-defense, non-arctic
    return 0.0, "Not relevant to arctic defense", []


async def filter_opportunities(
    opportunities: list[Opportunity],
    gemini_api_key: Optional[str] = None,
) -> tuple[list[Opportunity], list[Opportunity]]:
    """
    Filter and score opportunities for arctic defense relevance.
    Uses rule-based scoring (LLM disabled due to model availability).
    
    Returns:
        Tuple of (all_scored_opportunities, arctic_relevant_opportunities)
    """
    config = get_config()
    
    logger.info(f"Scoring {len(opportunities)} opportunities for arctic defense relevance...")
    
    scored_high = 0
    scored_medium = 0
    scored_low = 0
    excluded = 0
    
    for opp in opportunities:
        score, reasoning, keywords = score_opportunity(opp)
        opp.arctic_relevance_score = score
        opp.arctic_relevance_reasoning = reasoning
        opp.arctic_keywords_found = keywords
        
        if score >= 0.7:
            scored_high += 1
        elif score >= 0.3:
            scored_medium += 1
        elif score > 0:
            scored_low += 1
        else:
            excluded += 1
    
    logger.info(f"Scoring complete: {scored_high} high, {scored_medium} medium, {scored_low} low, {excluded} excluded")
    
    # Filter for arctic-relevant (score >= threshold)
    arctic_relevant = [
        opp for opp in opportunities 
        if opp.arctic_relevance_score >= config.arctic_relevance_threshold
    ]
    
    # Sort by relevance score
    arctic_relevant.sort(key=lambda x: x.arctic_relevance_score, reverse=True)
    
    logger.info(
        f"Arctic defense filtering complete: {len(arctic_relevant)} relevant (>={config.arctic_relevance_threshold}) out of {len(opportunities)} total"
    )
    
    return opportunities, arctic_relevant
