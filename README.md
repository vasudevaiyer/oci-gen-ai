# Step-by-Step: Client App Calling OCI GenAI Agent Endpoint for Weather

This guide covers one use case only:
- A client sends user input to an OCI Generative AI Agent endpoint.
- The agent uses a local function tool (`get_current_weather`) during ADK execution.
- The client receives the final weather answer.

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

## 4. Verify Local Tool Data (Optional but Recommended)

Run a local-only test before endpoint calls:

```bash
python /u01/scripts/agent_fucn_tool/oci_agent_weather_tool.py \
  --location "Chicago" \
  --tool-only
```

Expected behavior:
- Returns JSON with weather fields from `weather_static.json`.

## 5. Run the Client for One User Request

Use your endpoint OCID:

```bash
python /u01/scripts/agent_fucn_tool/genai_weather_client.py \
  --agent-endpoint-id "ocid1.genaiagentendpoint.oc1.us-chicago-1.xxxxx" \
  --input "What is the weather in Chicago?"
```

You can also pass an agent OCID (`ocid1.genaiagent...`):
- The script resolves the latest ACTIVE endpoint automatically.

## 6. Run the Client in Interactive Mode

```bash
python /u01/scripts/agent_fucn_tool/genai_weather_client.py \
  --agent-endpoint-id "ocid1.genaiagentendpoint.oc1.us-chicago-1.xxxxx"
```

Then type prompts like:
- `What is the weather in Austin?`
- `Tell me current weather for Tokyo.`

## 7. How This Matches the Oracle Function Tool Pattern

Execution pattern:
1. Your client calls the OCI agent endpoint with user input.
2. OCI returns required action for tool invocation (when needed).
3. ADK in your local client executes `get_current_weather`.
4. Tool result is sent back through ADK.
5. Final agent response is returned to the client.

Reference:
- https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/adk/api-reference/examples/agent-function-tool.htm

## 8. Common Errors and Fixes

- `FUNCTION_CALLING_REQUIRED_ACTION` without final answer:
  - Cause: calling from an environment that does not execute local function tools.
  - Fix: run through `genai_weather_client.py` (ADK runtime), not Console chat alone.

- Auth/config errors from OCI SDK:
  - Cause: invalid profile or config path.
  - Fix: verify `/home/opc/.oci/config`, profile name, and permissions.

- Unknown city/country in tool response:
  - Cause: location not present in `weather_static.json` mappings.
  - Fix: add mapping/record in `weather_static.json`.

## 9. Validate Scripts Compile

```bash
source /u01/venv/bin/activate
python -m py_compile /u01/scripts/agent_fucn_tool/oci_agent_weather_tool.py
python -m py_compile /u01/scripts/agent_fucn_tool/genai_weather_client.py
```

## 10. Minimal Integration Pattern (App -> Client)

If building a web/mobile backend, call the same client logic from your API layer:
1. Receive `location` or user prompt.
2. Call `Agent.run(input=...)` using the setup in `genai_weather_client.py`.
3. Return the agent response payload to the frontend.

This keeps the function tool execution in your controlled backend runtime.
