#!/usr/bin/env python3
"""
Create SearchAgent GPT Assistant with Actions via OpenAI API
"""

import os
import json
from openai import OpenAI

# Read OpenAI admin key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# System prompt
SYSTEM_PROMPT = """You are SearchAgent for the /search command in RSS News system.

Your tool: retrieve — GPT Action (REST API via OpenAPI)

Algorithm:
1. Parse user query and determine parameters:
   - query: user's search keywords
   - hours: time window (default: 24, can expand to 48, 72)
   - k: number of results (default: 10)
   - filters: optional {sources: [...], lang: "en"}
   - cursor: for pagination (null initially)

2. Call retrieve action with parameters

3. Auto-retry on empty results (max 3 attempts total):
   - If items array is empty and hours=24 → retry with hours=48
   - If still empty and hours=48 → retry with hours=72
   - If still empty → inform user "no results found"

4. Present results to user:
   - Show article titles with URLs
   - Show source domains and published dates
   - Show relevance scores if available
   - Highlight coverage and freshness metrics
   - If next_cursor exists → offer pagination

5. Return structured response:
   - Summary of findings
   - List of articles with snippets
   - Metadata (total found, coverage, freshness)
   - Next steps (pagination, refine query, etc.)

Guidelines:
- Be concise but informative
- Always show relevance_score to help user assess quality
- If coverage < 0.5, suggest expanding time window
- For pagination: use next_cursor to get more results
- Respect diagnostics.correlation_id for tracking

Example interaction:
User: "Find me news about AI regulation in EU"
SearchAgent:
1. Call retrieve(query="AI regulation EU", hours=24, k=10)
2. If empty → retry with hours=48
3. Present results with metadata
4. Suggest: "Want more results? I can search 72h or paginate."
"""

# Action schema (from search_openapi.yaml)
ACTION_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "Search API for GPT Actions",
        "description": "Search API endpoint for SearchAgent to retrieve news articles.",
        "version": "1.0.0"
    },
    "servers": [
        {
            "url": "https://rssnews-production-eaa2.up.railway.app"
        }
    ],
    "paths": {
        "/retrieve": {
            "post": {
                "operationId": "retrieve",
                "summary": "Retrieve news articles",
                "description": "Search for news articles based on query and filters.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["query"],
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Search query string"
                                    },
                                    "hours": {
                                        "type": "integer",
                                        "description": "Time window in hours (24, 48, or 72)",
                                        "default": 24
                                    },
                                    "k": {
                                        "type": "integer",
                                        "description": "Number of results to return",
                                        "default": 10
                                    },
                                    "filters": {
                                        "type": "object",
                                        "description": "Additional filters",
                                        "properties": {
                                            "sources": {
                                                "type": "array",
                                                "items": {"type": "string"}
                                            },
                                            "lang": {
                                                "type": "string",
                                                "enum": ["en", "ru", "auto"],
                                                "default": "auto"
                                            }
                                        }
                                    },
                                    "cursor": {
                                        "type": "string",
                                        "nullable": True,
                                        "description": "Pagination cursor"
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Successful retrieval",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["items", "total_available", "coverage", "freshness_stats", "diagnostics"],
                                    "properties": {
                                        "items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "title": {"type": "string"},
                                                    "url": {"type": "string"},
                                                    "source_domain": {"type": "string"},
                                                    "published_at": {"type": "string"},
                                                    "snippet": {"type": "string", "nullable": True},
                                                    "relevance_score": {"type": "number", "nullable": True}
                                                }
                                            }
                                        },
                                        "next_cursor": {"type": "string", "nullable": True},
                                        "total_available": {"type": "integer"},
                                        "coverage": {"type": "number"},
                                        "freshness_stats": {
                                            "type": "object",
                                            "properties": {
                                                "median_age_seconds": {"type": "number"},
                                                "window_hours": {"type": "integer"}
                                            }
                                        },
                                        "diagnostics": {
                                            "type": "object",
                                            "properties": {
                                                "total_results": {"type": "integer"},
                                                "offset": {"type": "integer"},
                                                "returned": {"type": "integer"},
                                                "has_more": {"type": "boolean"},
                                                "window": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


def create_assistant():
    """Create GPT Assistant with Actions"""

    print("🚀 Creating SearchAgent GPT Assistant...")
    print()

    try:
        # Create assistant
        assistant = client.beta.assistants.create(
            name="SearchAgent",
            description="News search agent with access to RSS news database via /retrieve API",
            instructions=SYSTEM_PROMPT,
            model="gpt-4-turbo-preview",  # or "gpt-4" if available
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "retrieve",
                        "description": "Search for news articles based on query and filters",
                        "parameters": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query string"
                                },
                                "hours": {
                                    "type": "integer",
                                    "description": "Time window in hours (24, 48, or 72)",
                                    "default": 24
                                },
                                "k": {
                                    "type": "integer",
                                    "description": "Number of results to return",
                                    "default": 10
                                },
                                "filters": {
                                    "type": "object",
                                    "description": "Additional filters (sources, lang)",
                                    "properties": {
                                        "sources": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Filter by source domains"
                                        },
                                        "lang": {
                                            "type": "string",
                                            "enum": ["en", "ru", "auto"],
                                            "default": "auto"
                                        }
                                    }
                                },
                                "cursor": {
                                    "type": "string",
                                    "description": "Pagination cursor from previous response"
                                }
                            }
                        }
                    }
                }
            ]
        )

        print("✅ Assistant created successfully!")
        print()
        print(f"Assistant ID: {assistant.id}")
        print(f"Name: {assistant.name}")
        print(f"Model: {assistant.model}")
        print(f"Tools: {len(assistant.tools)} tool(s)")
        print()

        # Save assistant info
        assistant_info = {
            "id": assistant.id,
            "name": assistant.name,
            "model": assistant.model,
            "created_at": assistant.created_at,
            "instructions": assistant.instructions[:100] + "...",
            "tools": [tool.type for tool in assistant.tools]
        }

        with open("assistant_info.json", "w") as f:
            json.dump(assistant_info, f, indent=2)

        print("💾 Assistant info saved to assistant_info.json")
        print()
        print("⚠️  IMPORTANT: GPT Actions через Assistants API работают иначе!")
        print("   Вместо GPT Actions нужно использовать Function Calling.")
        print()
        print("📋 Next steps:")
        print("   1. Используйте Assistant ID для создания Thread")
        print("   2. В коде обрабатывайте function calls к 'retrieve'")
        print("   3. Вызывайте ваш API вручную при function call")
        print()
        print("Или используйте веб-интерфейс для GPT Actions:")
        print("   https://platform.openai.com/playground/assistants")
        print()

        return assistant

    except Exception as e:
        print(f"❌ Error creating assistant: {e}")
        return None


if __name__ == "__main__":
    assistant = create_assistant()

    if assistant:
        print("✅ SUCCESS!")
        print()
        print(f"Assistant URL: https://platform.openai.com/playground/assistants/{assistant.id}")
