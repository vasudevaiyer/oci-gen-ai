# Step-by-Step: Function Tool Demo with OCI GenAI Agent Service

This project demonstrates OCI Agent **function-calling** with static weather data:
- A client app sends user input to an OCI Agent endpoint.
- OCI Agent requests `get_current_weather(...)`.
- ADK executes the local function from `weather_static.json`.
- The client receives the final agent answer.

## 1. What You Need

1. Python virtual environment at `/u01/venv`.
2. OCI SDK with ADK support installed in that venv.
3. OCI config file at `/home/opc/.oci/config`.
4. An active OCI GenAI Agent endpoint OCID (`ocid1.genaiagentendpoint...`) or agent OCID (`ocid1.genaiagent...`).
5. This folder available locally:
   - `/u01/scripts/agent_fucn_tool`

## 2. Files Used in This Flow

- `genai_weather_client.py`
  - Client entrypoint that sends prompts to OCI endpoint.
- `oci_agent_weather_tool.py`
  - Defines local function tool `get_current_weather(location)`.
  - Resolves endpoint if only agent OCID is provided.
- `weather_static.json`
  - Static weather data used by `get_current_weather`.

## 3. Activate Environment

```bash
source /u01/venv/bin/activate
```

## 4. One-Time Setup: Register/Sync Function Tool on Agent

Run this once to sync local function tool definition with the remote agent (`agent.setup()` is called internally):

```bash
python /u01/scripts/agent_fucn_tool/oci_agent_weather_tool.py \
  --location "Chicago" \
  --agent-endpoint-id "<agent_or_endpoint_ocid>"
```

What this does:
- Resolves endpoint OCID (if agent OCID is provided).
- Registers/synchronizes `get_current_weather` on the agent.
- Executes one sample prompt end-to-end.

## 5. Verify Local Tool Data (Optional but Recommended)

Run a local-only test before endpoint calls:

```bash
python /u01/scripts/agent_fucn_tool/oci_agent_weather_tool.py \
  --location "Chicago" \
  --tool-only
```

Expected behavior:
- Returns JSON with weather fields from `weather_static.json`.

## 6. Run the Client for One User Request

Use your endpoint OCID:

```bash
python /u01/scripts/agent_fucn_tool/genai_weather_client.py \
  --agent-endpoint-id "ocid1.genaiagentendpoint.oc1.us-chicago-1.xxxxx" \
  --input "What is the weather in Chicago?"
```

You can also pass an agent OCID (`ocid1.genaiagent...`):
- The script resolves the latest ACTIVE endpoint automatically.

## 7. Run the Client in Interactive Mode

```bash
python /u01/scripts/agent_fucn_tool/genai_weather_client.py \
  --agent-endpoint-id "ocid1.genaiagentendpoint.oc1.us-chicago-1.xxxxx"
```

Then type prompts like:
- `What is the weather in Austin?`
- `Tell me current weather for Tokyo.`

## 8. How This Matches the Oracle Function Tool Pattern

Execution pattern:
1. Your client calls the OCI agent endpoint with user input.
2. OCI returns required action for tool invocation (when needed).
3. ADK in your local client executes `get_current_weather`.
4. Tool result is sent back through ADK.
5. Final agent response is returned to the client.

Reference:
- https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/adk/api-reference/examples/agent-function-tool.htm

## 9. How a Client Application Uses This

### CLI client (already provided)

```bash
python /u01/scripts/agent_fucn_tool/genai_weather_client.py \
  --agent-endpoint-id "<agent_or_endpoint_ocid>" \
  --input "What is the weather in Tokyo?"
```

### Backend integration pattern

In your backend service, reuse the same flow from `genai_weather_client.py`:
1. Initialize `AgentClient`.
2. Create `Agent(..., tools=[get_current_weather])`.
3. Call `agent.setup()` on startup.
4. Call `agent.run(input=user_prompt)` per request.

This keeps tool execution in your application runtime (required for local function tools).

## 10. Common Errors and Fixes

- `FUNCTION_CALLING_REQUIRED_ACTION` without final answer:
  - Cause: calling from an environment that does not execute local function tools.
  - Fix: run through `genai_weather_client.py` (ADK runtime), not Console chat alone.

- Auth/config errors from OCI SDK:
  - Cause: invalid profile or config path.
  - Fix: verify `/home/opc/.oci/config`, profile name, and permissions.

- Unknown city/country in tool response:
  - Cause: location not present in `weather_static.json` mappings.
  - Fix: add mapping/record in `weather_static.json`.

## 11. Validate Scripts Compile

```bash
source /u01/venv/bin/activate
python -m py_compile /u01/scripts/agent_fucn_tool/oci_agent_weather_tool.py
python -m py_compile /u01/scripts/agent_fucn_tool/genai_weather_client.py
```

## 12. Data File

- `weather_static.json` is the only weather source for this demo.
- Update country records or city mappings there to change tool output.
