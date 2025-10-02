"""
Agents Node — Second step: run agents in parallel
Calls appropriate agents based on command type
"""

import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


async def agents_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute agents step (parallel execution)

    Input state:
        - command: str ("/trends", "/analyze", "/predict", "/competitors", "/synthesize")
        - params: Dict (with mode: keywords|sentiment|topics, or topic/domains/niche)
        - docs: List[Dict]
        - correlation_id: str

    Output state (adds):
        - agent_results: Dict[str, Any]
        - agents_meta: Dict
    """
    try:
        command = state.get("command")
        params = state.get("params", {})
        docs = state.get("docs", [])
        correlation_id = state.get("correlation_id", "unknown")

        if not docs:
            logger.warning("No docs available for agents")
            state["agent_results"] = {}
            return state

        logger.info(f"Agents node: command={command}, docs={len(docs)}")

        # Determine which agents to run
        agents_to_run = []

        if command == "/trends":
            # Trends enhanced: topic_modeler + sentiment_emotion
            agents_to_run = ["topic_modeler", "sentiment_emotion"]

            # Phase 2: Optional synthesis (if enabled in config)
            if params.get("enable_synthesis", False):
                # Synthesis runs after other agents complete
                pass  # Will be handled separately

        elif command == "/analyze":
            mode = params.get("mode", "keywords")

            if mode == "keywords":
                agents_to_run = ["keyphrase_mining"]
                # Optional: add query_expansion if docs > 3
                if len(docs) > 3:
                    agents_to_run.append("query_expansion")

            elif mode == "sentiment":
                agents_to_run = ["sentiment_emotion"]

            elif mode == "topics":
                agents_to_run = ["topic_modeler"]

        # Phase 2: NEW commands
        elif command == "/predict":
            # TrendForecaster
            agents_to_run = ["trend_forecaster"]

        elif command == "/competitors":
            # CompetitorNews
            agents_to_run = ["competitor_news"]

        elif command == "/synthesize":
            # SynthesisAgent (meta-analysis)
            agents_to_run = ["synthesis_agent"]

        # Run agents in parallel
        tasks = []
        for agent_name in agents_to_run:
            task = asyncio.create_task(
                _run_agent(agent_name, docs, correlation_id, state)
            )
            tasks.append((agent_name, task))

        # Wait for all agents
        agent_results = {}
        for agent_name, task in tasks:
            try:
                result = await task
                agent_results[agent_name] = result
                logger.info(f"Agent {agent_name} completed successfully")
            except Exception as e:
                logger.error(f"Agent {agent_name} failed: {e}")
                agent_results[agent_name] = {
                    "error": str(e),
                    "success": False
                }

        # Update state
        state["agent_results"] = agent_results
        state["agents_meta"] = {
            "agents_run": agents_to_run,
            "agents_succeeded": [
                name for name, result in agent_results.items()
                if result.get("success", True)
            ]
        }

        logger.info(f"Agents node completed: {len(agent_results)} agents")

        return state

    except Exception as e:
        logger.error(f"Agents node failed: {e}", exc_info=True)
        state["error"] = {
            "node": "agents",
            "code": "INTERNAL",
            "message": f"Failed to run agents: {e}"
        }
        return state


async def _run_agent(
    agent_name: str,
    docs: List[Dict[str, Any]],
    correlation_id: str,
    state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Run a single agent

    Args:
        agent_name: Name of agent to run
        docs: Retrieved documents
        correlation_id: Correlation ID for tracking
        state: Full state (for accessing other params)

    Returns:
        Agent result dict
    """
    try:
        logger.info(f"Running agent: {agent_name}")

        # Import agent module dynamically
        if agent_name == "keyphrase_mining":
            from core.agents.keyphrase_mining import run_keyphrase_mining
            result = await run_keyphrase_mining(docs, correlation_id)

        elif agent_name == "query_expansion":
            from core.agents.query_expansion import run_query_expansion
            result = await run_query_expansion(docs, correlation_id)

        elif agent_name == "sentiment_emotion":
            from core.agents.sentiment_emotion import run_sentiment_emotion
            result = await run_sentiment_emotion(docs, correlation_id)

        elif agent_name == "topic_modeler":
            from core.agents.topic_modeler import run_topic_modeler
            result = await run_topic_modeler(docs, correlation_id)

        # Phase 2: NEW agents
        elif agent_name == "trend_forecaster":
            from core.agents.trend_forecaster import run_trend_forecaster
            topic = state.get("params", {}).get("topic")
            window = state.get("window", "1w")
            result = await run_trend_forecaster(docs, topic, window, correlation_id)

        elif agent_name == "competitor_news":
            from core.agents.competitor_news import run_competitor_news
            domains = state.get("params", {}).get("domains")
            niche = state.get("params", {}).get("niche")
            result = await run_competitor_news(docs, domains, niche, correlation_id)

        elif agent_name == "synthesis_agent":
            from core.agents.synthesis_agent import run_synthesis_agent
            agent_outputs = state.get("agent_results", {})
            result = await run_synthesis_agent(agent_outputs, docs, correlation_id)

        else:
            raise ValueError(f"Unknown agent: {agent_name}")

        return result

    except Exception as e:
        logger.error(f"Agent {agent_name} execution failed: {e}", exc_info=True)
        raise