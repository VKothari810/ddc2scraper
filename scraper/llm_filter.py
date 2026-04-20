"""Gemini LLM filter for arctic relevance scoring"""
import json
import logging
from typing import Optional

from .config import (
    ARCTIC_KEYWORDS,
    ARCTIC_ADJACENT_KEYWORDS,
    get_config,
)
from .models import Opportunity

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an analyst for a defense technology company focused on arctic and cold-region operations. Your job is to evaluate whether a government solicitation or opportunity is relevant to arctic/cold-region defense needs.

Score each opportunity from 0.0 to 1.0:
- 1.0: Explicitly about arctic, polar, cold regions, or extreme cold operations
- 0.8: Strongly related (e.g., Alaska operations, CRREL, permafrost, ice, high-latitude)
- 0.6: Moderately related (e.g., extreme environment operations that could include cold, contested logistics in northern theaters, INDOPACOM/EUCOM cold-weather relevant)
- 0.4: Tangentially related (e.g., general resilience tech applicable to cold regions)
- 0.2: Weakly related (e.g., broad BAA where cold regions is one of many possible applications)
- 0.0: Not relevant to arctic/cold regions

Respond ONLY with valid JSON for each opportunity in this exact format:
{
  "scores": [
    {
      "id": "opportunity_id_here",
      "score": 0.8,
      "reasoning": "One sentence explaining why",
      "keywords_found": ["arctic", "cold weather", "Alaska"]
    }
  ]
}"""


def keyword_prefilter(opp: Opportunity) -> tuple[str, list[str]]:
    """
    Quick keyword-based pre-filter to categorize opportunities.
    
    Returns:
        Tuple of (category, keywords_found):
        - 'definite' - Contains arctic keywords, high priority for LLM
        - 'maybe' - Contains adjacent keywords, send to LLM
        - 'low' - No keywords but still defense-related, assign baseline score
    """
    text = f"{opp.title} {opp.description}".lower()
    
    # Also check agency/sub_agency fields
    if opp.agency:
        text += f" {opp.agency.lower()}"
    if opp.sub_agency:
        text += f" {opp.sub_agency.lower()}"
    if opp.office:
        text += f" {opp.office.lower()}"
    
    found_keywords = []

    for kw in ARCTIC_KEYWORDS:
        if kw.lower() in text:
            found_keywords.append(kw)
    
    if found_keywords:
        return "definite", found_keywords

    for kw in ARCTIC_ADJACENT_KEYWORDS:
        if kw.lower() in text:
            found_keywords.append(kw)
    
    if found_keywords:
        return "maybe", found_keywords

    return "low", []


async def score_opportunities_batch(
    opportunities: list[Opportunity],
    client,
) -> list[Opportunity]:
    """
    Score a batch of opportunities using Gemini.
    
    Args:
        opportunities: List of opportunities to score
        client: google.genai.Client instance
        
    Returns:
        Opportunities with arctic_relevance fields populated
    """
    if not opportunities:
        return []

    config = get_config()

    opp_texts = []
    for opp in opportunities:
        opp_texts.append(
            f"ID: {opp.id}\n"
            f"Title: {opp.title}\n"
            f"Agency: {opp.agency or 'Unknown'}\n"
            f"Description: {opp.description[:2000]}\n"
        )

    prompt = f"""Evaluate these {len(opportunities)} opportunities for arctic/cold-region relevance:

{chr(10).join(opp_texts)}

Return JSON with scores for all {len(opportunities)} opportunities."""

    try:
        response = await client.aio.models.generate_content(
            model=config.gemini_model,
            contents=[
                {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
                {"role": "model", "parts": [{"text": "I understand. I will evaluate opportunities for arctic relevance and respond with JSON only."}]},
                {"role": "user", "parts": [{"text": prompt}]},
            ],
        )

        response_text = response.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        scores_data = json.loads(response_text)
        scores_by_id = {s["id"]: s for s in scores_data.get("scores", [])}

        for opp in opportunities:
            if opp.id in scores_by_id:
                score_info = scores_by_id[opp.id]
                opp.arctic_relevance_score = float(score_info.get("score", 0.0))
                opp.arctic_relevance_reasoning = score_info.get("reasoning", "")
                opp.arctic_keywords_found = score_info.get("keywords_found", [])

        return opportunities

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return opportunities
    except Exception as e:
        logger.error(f"LLM scoring failed: {e}")
        return opportunities


async def filter_opportunities(
    opportunities: list[Opportunity],
    gemini_api_key: Optional[str] = None,
) -> tuple[list[Opportunity], list[Opportunity]]:
    """
    Filter and score opportunities for arctic relevance.
    
    Returns:
        Tuple of (all_scored_opportunities, arctic_relevant_opportunities)
    """
    config = get_config()
    api_key = gemini_api_key or config.gemini_api_key

    if not api_key:
        logger.warning("No Gemini API key provided, returning unscored opportunities")
        return opportunities, []

    definite = []
    maybe = []
    low = []

    for opp in opportunities:
        category, keywords = keyword_prefilter(opp)
        if category == "definite":
            opp.arctic_keywords_found = keywords
            definite.append(opp)
        elif category == "maybe":
            opp.arctic_keywords_found = keywords
            maybe.append(opp)
        else:
            low.append(opp)

    logger.info(
        f"Pre-filter results: {len(definite)} definite, {len(maybe)} maybe, {len(low)} low priority"
    )

    # Score all opportunities, not just definite/maybe
    to_score = definite + maybe + low

    if not to_score:
        logger.info("No opportunities to score")
        return opportunities, []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
    except ImportError:
        logger.error("google-genai package not installed")
        return opportunities, []
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        return opportunities, []

    scored = []
    batch_size = config.llm_batch_size

    for i in range(0, len(to_score), batch_size):
        batch = to_score[i : i + batch_size]
        logger.info(f"Scoring batch {i // batch_size + 1} ({len(batch)} opportunities)")
        scored_batch = await score_opportunities_batch(batch, client)
        scored.extend(scored_batch)

    # Apply baseline scores for opportunities that weren't scored by LLM
    for opp in definite:
        if opp.arctic_relevance_score == 0.0:
            opp.arctic_relevance_score = 0.7
            opp.arctic_relevance_reasoning = f"Contains arctic keywords: {', '.join(opp.arctic_keywords_found or [])}"
    
    for opp in maybe:
        if opp.arctic_relevance_score == 0.0:
            opp.arctic_relevance_score = 0.3
            opp.arctic_relevance_reasoning = f"Contains related keywords: {', '.join(opp.arctic_keywords_found or [])}"
    
    for opp in low:
        if opp.arctic_relevance_score == 0.0:
            opp.arctic_relevance_score = 0.1
            opp.arctic_relevance_reasoning = "Defense opportunity - potential arctic application"

    all_opportunities = scored

    arctic_relevant = [
        opp for opp in all_opportunities if opp.arctic_relevance_score >= config.arctic_relevance_threshold
    ]

    arctic_relevant.sort(key=lambda x: x.arctic_relevance_score, reverse=True)

    logger.info(
        f"LLM filtering complete: {len(arctic_relevant)} arctic-relevant (>={config.arctic_relevance_threshold}) out of {len(all_opportunities)} total"
    )

    return all_opportunities, arctic_relevant
