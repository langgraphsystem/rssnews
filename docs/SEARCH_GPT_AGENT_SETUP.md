# SearchAgent GPT Setup Guide

## Overview

This guide shows how to configure SearchAgent in OpenAI platform using GPT Actions.

---

## Step 1: Create GPT Agent

### Option A: Using ChatGPT (GPT Builder)

1. Go to https://chat.openai.com/
2. Click **Explore GPTs** → **Create**
3. Name: **SearchAgent**
4. Description: **News search agent with auto-retry and pagination**

### Option B: Using OpenAI Assistants API

```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_API_KEY")

assistant = client.beta.assistants.create(
    name="SearchAgent",
    instructions=SYSTEM_PROMPT,  # See below
    model="gpt-4-turbo-preview",
    tools=[{
        "type": "function",
        "function": {
            # Will be configured via Actions
        }
    }]
)
```

---

## Step 2: Configure GPT Actions

### 2.1 Add Action

1. In GPT configuration, go to **Actions**
2. Click **Create new action**
3. **Authentication**:
   - If using Cloudflare Access: **API Key** (Custom Headers)
   - If no auth: **None**

### 2.2 Import OpenAPI Schema

**Method 1: Upload File**
- Upload `api/search_openapi.yaml`

**Method 2: Paste Schema**
- Copy contents of `search_openapi.yaml`
- Paste into schema editor

**Method 3: Import from URL**
- If you host OpenAPI spec publicly:
- URL: `https://search-api.yourdomain.com/openapi.json`

### 2.3 Replace Hostname

In the schema, replace:
```yaml
servers:
  - url: https://YOUR_HOSTNAME.trycloudflare.com
```

With your actual URL:
```yaml
servers:
  - url: https://search-api.yourdomain.com
```

### 2.4 Configure Authentication (if using Cloudflare Access)

**Auth Type:** Custom Headers

**Header 1:**
- Name: `CF-Access-Client-Id`
- Value: `YOUR_CLIENT_ID`

**Header 2:**
- Name: `CF-Access-Client-Secret`
- Value: `YOUR_CLIENT_SECRET`

---

## Step 3: Add System Prompt

Copy this exact prompt into **Instructions**:

```
You are SearchAgent for the /search command.

Your tool: retrieve — GPT Action (REST via OpenAPI) with base URL https://search-api.yourdomain.com

Always return exactly ONE JSON object following the specified schema (below). Do not write essays.

## Input from Bot

- command="/search"
- query: string
- options: hours?: number=24, k?: number=10, filters?: object, cursor?: string, correlation_id: string

## Tool: retrieve

Method: POST /retrieve on https://search-api.yourdomain.com

Request body:
{
  "query": "...",
  "hours": 24,
  "k": 10,
  "filters": {},
  "cursor": null,
  "correlation_id": "..."
}

Response from tool:
{
  "items": [{"id", "title", "url", "snippet", "ts", "source", "score"}],
  "next_cursor": "string|null",
  "coverage": 0.0,
  "freshness_stats": {"median_sec": 0}
}

Tool errors: NO_RESULTS | RATE_LIMIT | INVALID_FILTER | SERVER_ERROR + message

## Algorithm

1. Form parameters: if not specified — hours=24, k=10, filters={}, cursor=null
2. Call retrieve
3. If items empty — perform up to 2 additional iterations (total ≤3 tool calls):
   - Increase hours → 48, then 72
   - Relax strictest filters
   - If needed, rephrase query (synonyms/keywords)
4. Sort by relevance/freshness (if tool doesn't sort)
5. If next_cursor exists — return it as-is (for "More" button)
6. Final response — only cards and metadata in JSON (see schema below)
7. In answer_md add 1-2 lines of query refinement hints (optional)

## Response Format (Strict Structured Output)

Return ONE JSON object with exactly these fields:

{
  "plan": ["step 1 ...", "step 2 ..."],
  "tool_calls": [
    {
      "tool": "action",
      "name": "retrieve",
      "endpoint": "POST /retrieve",
      "params_used": {"query":"...", "hours":24, "k":10, "filters":{}, "cursor":null},
      "status": "ok|error"
    }
  ],
  "data": {
    "items": [
      {"id":"...","title":"...","url":"...","snippet":"...","ts":"2025-10-06T12:00:00Z","source":"...","score":0.0}
    ],
    "next_cursor": null,
    "metrics": {"coverage": 0.0, "freshness_median_sec": 0}
  },
  "answer_md": "brief hint (1-2 lines, optional)",
  "next_steps": ["example: increase hours to 48; narrow sources"],
  "diagnostics": {"last_query":"...", "retries":0, "latency_ms":0, "spent_tokens":0},
  "error": {"code": null, "message": null}
}

## Requirements

- Follow order: plan → tool_calls → data → answer_md/next_steps/diagnostics → error
- In tool_calls.params_used do NOT include secrets/keys — only request parameters
- If after all iterations empty — return error.code="NO_RESULTS" and concrete recommendations (which parameters to change)

## Pagination

If user requests "More", call retrieve with same query and received cursor, then return new next_cursor.

## Examples

### Example 1: Basic Search
User: /search AI regulation

Your response:
{
  "plan": ["Call retrieve with query='AI regulation', hours=24, k=10"],
  "tool_calls": [{
    "tool": "action",
    "name": "retrieve",
    "endpoint": "POST /retrieve",
    "params_used": {"query":"AI regulation", "hours":24, "k":10, "filters":{}, "cursor":null},
    "status": "ok"
  }],
  "data": {
    "items": [
      {"id":"art1", "title":"EU AI Act passed", "url":"https://europa.eu/...", "snippet":"...", "ts":"2025-10-05T14:00:00Z", "source":"europa.eu", "score":0.95},
      ...9 more items...
    ],
    "next_cursor": "b2Zmc2V0OjEw",
    "metrics": {"coverage": 1.0, "freshness_median_sec": 43200}
  },
  "answer_md": "Found 10 recent articles on AI regulation. Use 'More' for additional results.",
  "next_steps": ["Filter by source: site:europa.eu", "Expand time: hours=48"],
  "diagnostics": {"last_query":"AI regulation", "retries":0, "latency_ms":450, "spent_tokens":120},
  "error": {"code": null, "message": null}
}

### Example 2: No Results with Auto-Retry
User: /search obscure topic

Your response after 3 attempts (24h → 48h → 72h):
{
  "plan": [
    "Attempt 1: hours=24",
    "Attempt 2: hours=48 (no results)",
    "Attempt 3: hours=72 (no results)"
  ],
  "tool_calls": [
    {"tool":"action", "name":"retrieve", "params_used":{"query":"obscure topic","hours":24}, "status":"error"},
    {"tool":"action", "name":"retrieve", "params_used":{"query":"obscure topic","hours":48}, "status":"error"},
    {"tool":"action", "name":"retrieve", "params_used":{"query":"obscure topic","hours":72}, "status":"error"}
  ],
  "data": {
    "items": [],
    "next_cursor": null,
    "metrics": {"coverage": 0.0, "freshness_median_sec": 0}
  },
  "answer_md": null,
  "next_steps": [
    "Try broader query: 'topic' instead of 'obscure topic'",
    "Increase time window: hours=168 (1 week)",
    "Rephrase with synonyms"
  ],
  "diagnostics": {"last_query":"obscure topic", "retries":2, "latency_ms":1200, "spent_tokens":180},
  "error": {"code": "NO_RESULTS", "message": "No articles found after 3 attempts (24h, 48h, 72h)"}
}

### Example 3: Pagination
User: More

Your response:
{
  "plan": ["Call retrieve with cursor from previous response"],
  "tool_calls": [{
    "tool": "action",
    "name": "retrieve",
    "endpoint": "POST /retrieve",
    "params_used": {"query":"AI regulation", "hours":24, "k":10, "cursor":"b2Zmc2V0OjEw"},
    "status": "ok"
  }],
  "data": {
    "items": [...10 more items...],
    "next_cursor": "b2Zmc2V0OjIw",
    "metrics": {"coverage": 0.85, "freshness_median_sec": 86400}
  },
  "answer_md": "Next 10 results. Coverage: 85%",
  "next_steps": [],
  "diagnostics": {"last_query":"AI regulation", "retries":0, "latency_ms":380, "spent_tokens":110},
  "error": {"code": null, "message": null}
}
```

**Important:** Replace `https://search-api.yourdomain.com` with your actual Cloudflare Tunnel URL.

---

## Step 4: Enable Structured Outputs

### Option A: In GPT Settings

1. Go to **Settings** → **Response Format**
2. Select **JSON object**
3. Add JSON Schema for response structure

### Option B: Via API

```python
assistant = client.beta.assistants.create(
    name="SearchAgent",
    instructions=SYSTEM_PROMPT,
    model="gpt-4-turbo-preview",
    response_format={"type": "json_object"}
)
```

### JSON Schema for Response

```json
{
  "type": "object",
  "properties": {
    "plan": {"type": "array", "items": {"type": "string"}},
    "tool_calls": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tool": {"type": "string"},
          "name": {"type": "string"},
          "endpoint": {"type": "string"},
          "params_used": {"type": "object"},
          "status": {"type": "string", "enum": ["ok", "error"]}
        }
      }
    },
    "data": {
      "type": "object",
      "properties": {
        "items": {"type": "array"},
        "next_cursor": {"type": ["string", "null"]},
        "metrics": {"type": "object"}
      }
    },
    "answer_md": {"type": ["string", "null"]},
    "next_steps": {"type": "array", "items": {"type": "string"}},
    "diagnostics": {"type": "object"},
    "error": {"type": "object"}
  },
  "required": ["plan", "tool_calls", "data", "diagnostics", "error"]
}
```

---

## Step 5: Test the Agent

### Test 1: Basic Search

**Input:**
```
/search AI regulation
```

**Expected Behavior:**
1. Agent calls `retrieve` with `hours=24, k=10`
2. Returns JSON with 10 items
3. Includes `next_cursor` if more results available

### Test 2: No Results (Auto-Retry)

**Input:**
```
/search extremely obscure topic that doesn't exist
```

**Expected Behavior:**
1. Attempt 1: `hours=24` → NO_RESULTS
2. Attempt 2: `hours=48` → NO_RESULTS
3. Attempt 3: `hours=72` → NO_RESULTS
4. Returns error with recommendations

### Test 3: Pagination

**Input 1:**
```
/search Bitcoin
```

**Agent returns:** `next_cursor: "b2Zmc2V0OjEw"`

**Input 2:**
```
More
```

**Expected Behavior:**
- Agent calls `retrieve` with `cursor="b2Zmc2V0OjEw"`
- Returns next 10 results

---

## Step 6: Integrate with Telegram Bot

Add handler in `bot_service/advanced_bot.py`:

```python
async def handle_search_command(self, chat_id: str, user_id: str, args: List[str]):
    """
    Handle /search command via SearchAgent

    Usage: /search <query> [hours=24] [k=10]
    """
    if not args:
        await self._send_message(chat_id, "Usage: /search <query> [hours=24] [k=10]")
        return

    query = " ".join(args)
    correlation_id = f"search-{user_id}-{int(time.time())}"

    # Show typing indicator
    await self._send_message(chat_id, f"🔍 Searching for: {query}...")

    try:
        # Call OpenAI SearchAgent
        from openai import OpenAI

        client = OpenAI()

        # Create thread
        thread = client.beta.threads.create()

        # Add message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f'/search query="{query}" correlation_id="{correlation_id}"'
        )

        # Run assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id="asst_YOUR_ASSISTANT_ID"  # Replace with actual ID
        )

        # Wait for completion
        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(1)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        # Get response
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        response_text = messages.data[0].content[0].text.value

        # Parse JSON response
        import json
        response_data = json.loads(response_text)

        # Format results
        if response_data.get("error", {}).get("code"):
            # Error case
            error_msg = response_data["error"]["message"]
            recommendations = "\n".join(f"• {step}" for step in response_data.get("next_steps", []))

            await self._send_message(
                chat_id,
                f"❌ {error_msg}\n\n**Try:**\n{recommendations}"
            )
        else:
            # Success case
            items = response_data["data"]["items"]
            metrics = response_data["data"]["metrics"]

            # Build message
            msg = f"**Search Results for '{query}'**\n\n"
            msg += f"Found {len(items)} articles (coverage: {metrics['coverage']*100:.0f}%)\n\n"

            for i, item in enumerate(items[:5], 1):  # Show top 5
                msg += f"{i}. **{item['title']}**\n"
                msg += f"   {item['source']} • {item['ts'][:10]}\n"
                msg += f"   {item['url']}\n\n"

            # Add "More" button if cursor exists
            next_cursor = response_data["data"].get("next_cursor")
            if next_cursor:
                msg += f"[More results available - /search_more {correlation_id}]"

            await self._send_message(chat_id, msg)

    except Exception as e:
        logger.error(f"Search command failed: {e}", exc_info=True)
        await self._send_message(chat_id, f"❌ Search failed: {str(e)}")
```

---

## Step 7: Monitor Usage

### OpenAI Dashboard

1. Go to https://platform.openai.com/usage
2. View:
   - API calls per day
   - Token usage
   - Costs

### Cloudflare Analytics

1. Go to **Cloudflare Zero Trust** → **Access** → **Audit Logs**
2. Filter by Application: `Search API`
3. View:
   - Request count
   - Response times
   - Error rates

---

## Troubleshooting

### Agent Not Calling retrieve

**Symptoms:** Agent responds with text instead of calling tool

**Solutions:**
1. Check OpenAPI schema is correctly imported
2. Verify action is enabled in GPT settings
3. Ensure system prompt mentions "call retrieve"

### Authentication Errors (403)

**Symptoms:** `{"code": "SERVER_ERROR", "message": "Forbidden"}`

**Solutions:**
1. Verify Cloudflare Access headers in GPT Action settings
2. Check Service Token is valid
3. Test manually with curl:
```bash
curl -H "CF-Access-Client-Id: ID" -H "CF-Access-Client-Secret: SECRET" https://...
```

### Invalid JSON Response

**Symptoms:** Agent returns malformed JSON

**Solutions:**
1. Enable **Structured Outputs** in GPT settings
2. Add JSON schema validation
3. Emphasize "ONE JSON object" in system prompt

---

## Production Checklist

- [ ] Cloudflare Tunnel running (`cloudflared tunnel run search-api`)
- [ ] Search API running (`python api/search_api.py`)
- [ ] OpenAPI schema updated with correct hostname
- [ ] GPT Action configured with authentication
- [ ] System prompt added
- [ ] Structured outputs enabled
- [ ] Test search working (`/search test query`)
- [ ] Test pagination working (`More`)
- [ ] Test auto-retry on empty results
- [ ] Monitoring enabled (OpenAI + Cloudflare dashboards)

---

## Next Steps

1. **Add to Telegram bot:** Integrate `/search` command handler
2. **Add metrics:** Track search queries and results
3. **Add caching:** Cache frequent queries (optional)
4. **Add filters UI:** Buttons for `hours`, `sources` filters
5. **Add history:** Store user search history

---

## Summary

**SearchAgent Setup:**
1. ✅ Create GPT in OpenAI platform
2. ✅ Import OpenAPI schema (`search_openapi.yaml`)
3. ✅ Configure authentication (Cloudflare Access)
4. ✅ Add system prompt
5. ✅ Enable structured outputs
6. ✅ Test with sample queries
7. ✅ Integrate with Telegram bot

**Your URLs:**
- Search API: `https://search-api.yourdomain.com`
- OpenAPI spec: `https://search-api.yourdomain.com/openapi.json` (if hosted)
- Assistant ID: `asst_YOUR_ASSISTANT_ID`

**Ready to use `/search` command!** 🚀
