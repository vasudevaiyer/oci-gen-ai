#!/usr/bin/env python3
"""
OCI GenAI Agent weather tool example.

Usage:
  source /u01/venv/bin/activate
  python oci_agent_weather_tool.py --location "Austin, TX"
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

import oci
from oci.addons.adk import Agent, AgentClient, tool
from oci.generative_ai_agent import GenerativeAiAgentClient


DEFAULT_AGENT_ENDPOINT_ID = (
    "ocid1.genaiagent.oc1.us-chicago-1......."
)
DEFAULT_OCI_CONFIG = "/home/opc/.oci/config"
DEFAULT_STATIC_WEATHER_FILE = str(Path(__file__).with_name("weather_static.json"))


@tool(
    name="get_current_weather",
    description="Get current weather for a given location.",
)
def get_current_weather(location: str) -> Dict[str, Any]:
    """Returns weather from local static JSON data for demo purposes."""
    if not location or not location.strip():
        return {"error": "location is required"}

    safe_location = location.strip()
    normalized = safe_location.lower()

    try:
        data = json.loads(Path(DEFAULT_STATIC_WEATHER_FILE).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"Failed to read static weather file: {exc}"}

    countries = data.get("countries", {})
    city_map = data.get("city_to_country", {})
    key = city_map.get(normalized, normalized)

    if key not in countries:
        return {
            "error": "Static weather data is available only for configured demo countries/cities.",
            "supported_countries": sorted(countries.keys()),
        }

    record = countries[key]

    return {
        "location": safe_location,
        "country": key.title(),
        "condition": record.get("condition"),
        "temperature_c": record.get("temperature_c"),
        "humidity_percent": record.get("humidity_percent"),
        "source": "static_demo_json",
    }


def resolve_agent_endpoint_id(
    *,
    agent_or_endpoint_id: str,
    config_path: str,
    profile: str,
    region: str | None,
) -> str:
    """Return an agent endpoint OCID, resolving from agent OCID if needed."""
    if ".genaiagentendpoint." in agent_or_endpoint_id:
        return agent_or_endpoint_id
    if ".genaiagent." not in agent_or_endpoint_id:
        raise ValueError(
            "OCID must be either genaiagentendpoint or genaiagent."
        )

    cfg = oci.config.from_file(config_path, profile)
    effective_region = region or cfg.get("region")
    if effective_region:
        cfg["region"] = effective_region

    mgmt_client = GenerativeAiAgentClient(cfg)
    agent = mgmt_client.get_agent(agent_or_endpoint_id).data
    compartment_id = agent.compartment_id

    response = mgmt_client.list_agent_endpoints(
        compartment_id=compartment_id,
        agent_id=agent_or_endpoint_id,
        lifecycle_state="ACTIVE",
        sort_by="timeCreated",
        sort_order="DESC",
        limit=1,
    )
    collection = response.data
    endpoints = getattr(collection, "items", None) or []
    if not endpoints:
        raise RuntimeError(
            f"No ACTIVE agent endpoints found for agent {agent_or_endpoint_id} "
            f"in compartment {compartment_id}."
        )
    return endpoints[0].id


def main() -> None:
    global DEFAULT_STATIC_WEATHER_FILE

    parser = argparse.ArgumentParser(
        description="Run OCI GenAI Agent with a custom weather tool."
    )
    parser.add_argument(
        "--location",
        required=True,
        help="Location name, e.g., 'Seattle, WA'",
    )
    parser.add_argument(
        "--agent-endpoint-id",
        default=os.getenv("OCI_AGENT_ENDPOINT_ID", DEFAULT_AGENT_ENDPOINT_ID),
        help="OCI GenAI Agent endpoint OCID.",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("OCI_PROFILE", "DEFAULT"),
        help="OCI CLI profile name.",
    )
    parser.add_argument(
        "--config",
        default=os.getenv("OCI_CONFIG_FILE", DEFAULT_OCI_CONFIG),
        help="Path to OCI config file.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("OCI_REGION"),
        help="OCI region, e.g., us-chicago-1. Auto-derived from agent endpoint if omitted.",
    )
    parser.add_argument(
        "--tool-only",
        action="store_true",
        help="Run only the weather tool function locally without calling OCI Agent.",
    )
    parser.add_argument(
        "--static-file",
        default=os.getenv("STATIC_WEATHER_FILE", DEFAULT_STATIC_WEATHER_FILE),
        help="Path to static weather JSON file.",
    )
    args = parser.parse_args()

    DEFAULT_STATIC_WEATHER_FILE = args.static_file

    if args.tool_only:
        print(json.dumps(get_current_weather(args.location), indent=2))
        return

    region = args.region
    if not region:
        match = re.search(r"\.oc1\.([a-z0-9-]+)\.", args.agent_endpoint_id)
        if match:
            region = match.group(1)

    resolved_endpoint_id = resolve_agent_endpoint_id(
        agent_or_endpoint_id=args.agent_endpoint_id,
        config_path=args.config,
        profile=args.profile,
        region=region,
    )
    if resolved_endpoint_id != args.agent_endpoint_id:
        print(f"Resolved endpoint OCID: {resolved_endpoint_id}")

    client = AgentClient(
        auth_type="api_key",
        config=args.config,
        profile=args.profile,
        region=region,
    )

    agent = Agent(
        agent_endpoint_id=resolved_endpoint_id,
        client=client,
        instructions=(
            "Use get_current_weather for weather requests. "
            "This tool reads static demo weather data from JSON."
        ),
        tools=[get_current_weather],
    )
    agent.setup()

    prompt = (
        f"What is the current weather in {args.location}? "
        "Use the get_current_weather tool and summarize the result."
    )
    response = agent.run(input=prompt)
    response.pretty_print()


if __name__ == "__main__":
    main()
