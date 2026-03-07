#!/usr/bin/env python3
"""
Provision an OCI GenAI Agent HTTP endpoint weather tool (Console-executable).

This configures a server-side tool backed by wttr.in via OpenAPI, so OCI Console
can invoke the tool without any local ADK process.
"""

from __future__ import annotations

import argparse
import textwrap
from typing import Iterable

import oci
from oci.core import VirtualNetworkClient
from oci.generative_ai_agent import GenerativeAiAgentClient
from oci.generative_ai_agent.models import (
    ApiSchemaInlineInputLocation,
    CreateToolDetails,
    HttpEndpointAuthConfig,
    HttpEndpointAuthSource,
    HttpEndpointNoAuthScopeConfig,
    HttpEndpointToolConfig,
    UpdateToolDetails,
)


DEFAULT_AGENT_ID = (
    "ocid1.genaiagent.oc1.us-chicago-1."
    "amaaaaaaimfwupqaiqvrm5pmgcqetm3yvrykiajvwrvdpgxkmxapls3egraa"
)
DEFAULT_CONFIG = "/home/opc/.oci/config"
DEFAULT_PROFILE = "DEFAULT"
DEFAULT_REGION = "us-chicago-1"
DEFAULT_TOOL_DISPLAY_NAME = "weather_http_endpoint"


def build_openapi_schema() -> str:
    return textwrap.dedent(
        """
        openapi: 3.0.3
        info:
          title: Weather API
          version: "1.0"
          description: Get current weather by location using wttr.in
        servers:
          - url: https://wttr.in
        paths:
          /{location}:
            get:
              operationId: get_current_weather_http
              summary: Get current weather for a location
              parameters:
                - in: path
                  name: location
                  required: true
                  schema:
                    type: string
                  description: City/region query (for example, Chicago, IL)
                - in: query
                  name: format
                  required: true
                  schema:
                    type: string
                    enum: ["j1"]
                    default: j1
                  description: Must be j1 for JSON response
              responses:
                "200":
                  description: Current weather payload
                  content:
                    application/json:
                      schema:
                        type: object
                        additionalProperties: true
        """
    ).strip()


def resolve_subnet_id(
    client: GenerativeAiAgentClient,
    network_client: VirtualNetworkClient,
    agent_id: str,
    compartment_id: str,
    explicit_subnet_id: str | None,
) -> str | None:
    if explicit_subnet_id:
        return explicit_subnet_id

    endpoints = client.list_agent_endpoints(
        compartment_id=compartment_id,
        agent_id=agent_id,
        lifecycle_state="ACTIVE",
        sort_by="timeCreated",
        sort_order="DESC",
        limit=10,
    ).data
    items = getattr(endpoints, "items", None) or []
    for ep in items:
        if getattr(ep, "subnet_id", None):
            return ep.subnet_id

    # Fallback: pick an AVAILABLE subnet from the same compartment.
    subnets = network_client.list_subnets(
        compartment_id=compartment_id,
        lifecycle_state="AVAILABLE",
    ).data
    if not subnets:
        return None

    ranked = sorted(
        subnets,
        key=lambda s: (
            0
            if any(
                token in (s.display_name or "").lower()
                for token in ("web", "public", "ingress", "dmz")
            )
            else 1,
            0 if not getattr(s, "prohibit_public_ip_on_vnic", True) else 1,
            s.time_created,
        ),
    )
    return ranked[0].id


def list_agent_tools(client: GenerativeAiAgentClient, compartment_id: str, agent_id: str):
    coll = client.list_tools(compartment_id=compartment_id, agent_id=agent_id).data
    return getattr(coll, "items", None) or []


def iter_local_function_tool_ids_to_delete(
    client: GenerativeAiAgentClient,
    tool_summaries: Iterable,
) -> Iterable[str]:
    function_names_to_remove = {"get_weather", "get_current_weather"}
    for tool_summary in tool_summaries:
        full_tool = client.get_tool(tool_summary.id).data
        cfg = full_tool.tool_config
        if getattr(cfg, "tool_config_type", None) != "FUNCTION_CALLING_TOOL_CONFIG":
            continue
        function_name = getattr(getattr(cfg, "function", None), "name", None)
        if function_name in function_names_to_remove:
            yield full_tool.id


def upsert_http_weather_tool(
    client: GenerativeAiAgentClient,
    *,
    agent_id: str,
    compartment_id: str,
    display_name: str,
    subnet_id: str | None,
) -> str:
    if not subnet_id:
        raise RuntimeError(
            "HTTP endpoint tool requires subnet_id. Provide --subnet-id or ensure "
            "a subnet can be auto-discovered in the agent compartment."
        )

    api_schema = ApiSchemaInlineInputLocation(content=build_openapi_schema())
    auth_cfg = HttpEndpointAuthConfig(
        http_endpoint_auth_sources=[
            HttpEndpointAuthSource(
                http_endpoint_auth_scope="AGENT",
                http_endpoint_auth_scope_config=HttpEndpointNoAuthScopeConfig(),
            )
        ]
    )

    tool_cfg = HttpEndpointToolConfig(
        api_schema=api_schema,
        http_endpoint_auth_config=auth_cfg,
        subnet_id=subnet_id,
    )
    description = (
        "Console-executable weather tool backed by wttr.in over HTTP endpoint "
        "(no local ADK function execution required)."
    )

    tools = list_agent_tools(client, compartment_id, agent_id)
    existing = next((t for t in tools if t.display_name == display_name), None)
    if existing:
        client.update_tool(
            tool_id=existing.id,
            update_tool_details=UpdateToolDetails(
                display_name=display_name,
                description=description,
                tool_config=tool_cfg,
            ),
        )
        return existing.id

    created = client.create_tool(
        create_tool_details=CreateToolDetails(
            display_name=display_name,
            description=description,
            agent_id=agent_id,
            compartment_id=compartment_id,
            tool_config=tool_cfg,
        )
    ).data
    return created.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup OCI HTTP weather tool.")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--display-name", default=DEFAULT_TOOL_DISPLAY_NAME)
    parser.add_argument(
        "--subnet-id",
        default=None,
        help="Optional subnet OCID for HTTP endpoint egress; auto-detected if omitted.",
    )
    parser.add_argument(
        "--cleanup-local-function-tools",
        action="store_true",
        help="Delete get_weather/get_current_weather local function tools from agent.",
    )
    args = parser.parse_args()

    cfg = oci.config.from_file(args.config, args.profile)
    cfg["region"] = args.region
    client = GenerativeAiAgentClient(cfg)
    network_client = VirtualNetworkClient(cfg)

    agent = client.get_agent(args.agent_id).data
    compartment_id = agent.compartment_id

    subnet_id = resolve_subnet_id(
        client=client,
        network_client=network_client,
        agent_id=args.agent_id,
        compartment_id=compartment_id,
        explicit_subnet_id=args.subnet_id,
    )

    tool_id = upsert_http_weather_tool(
        client,
        agent_id=args.agent_id,
        compartment_id=compartment_id,
        display_name=args.display_name,
        subnet_id=subnet_id,
    )
    print(f"HTTP weather tool ready: {tool_id}")
    if subnet_id:
        print(f"Using subnet: {subnet_id}")
    else:
        print("No subnet provided/detected; tool created without subnet_id.")

    if args.cleanup_local_function_tools:
        tools = list_agent_tools(client, compartment_id, args.agent_id)
        to_delete = list(iter_local_function_tool_ids_to_delete(client, tools))
        for tool_id in to_delete:
            client.delete_tool(tool_id)
            print(f"Deleted local function tool: {tool_id}")
        if not to_delete:
            print("No local function tools found for cleanup.")


if __name__ == "__main__":
    main()
