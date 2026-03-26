#!/usr/bin/env python3
"""
Apply static weather records to an OCI GenAI Agent instruction.

This script updates the agent routing instruction so weather responses come from
fixed records (no external weather tool/API calls needed).
"""

from __future__ import annotations

import argparse
import json
from typing import Dict

import oci
from oci.generative_ai_agent import GenerativeAiAgentClient
from oci.generative_ai_agent.models import LlmConfig, LlmCustomization, UpdateAgentDetails


DEFAULT_AGENT_ID = (
    "ocid1.genaiagent.oc1.us-chicago-1........"
)
DEFAULT_CONFIG = "/home/opc/.oci/config"
DEFAULT_PROFILE = "DEFAULT"
DEFAULT_REGION = "us-chicago-1"

DEFAULT_RECORDS: Dict[str, Dict[str, str | int]] = {
    "United States": {
        "condition": "Partly Cloudy",
        "temperature_c": 12,
        "humidity_percent": 58,
    },
    "India": {
        "condition": "Sunny",
        "temperature_c": 30,
        "humidity_percent": 44,
    },
    "United Kingdom": {
        "condition": "Light Rain",
        "temperature_c": 9,
        "humidity_percent": 76,
    },
    "Japan": {
        "condition": "Clear",
        "temperature_c": 15,
        "humidity_percent": 50,
    },
    "Australia": {
        "condition": "Warm Breeze",
        "temperature_c": 24,
        "humidity_percent": 40,
    },
}


WEATHER_TOOL_NAMES = {
    "weather_http_endpoint",
    "get_weather",
    "get_current_weather",
}


def load_records(args: argparse.Namespace) -> Dict[str, Dict[str, str | int]]:
    if args.records_file:
        with open(args.records_file, "r", encoding="utf-8") as f:
            return json.load(f)
    if args.records_json:
        return json.loads(args.records_json)
    return DEFAULT_RECORDS


def build_instruction(records: Dict[str, Dict[str, str | int]]) -> str:
    lines = []
    for country, values in records.items():
        lines.append(
            f"{country}: condition={values['condition']}, "
            f"temperature_c={values['temperature_c']}, "
            f"humidity_percent={values['humidity_percent']}"
        )

    supported = ", ".join(records.keys())
    joined_lines = "; ".join(lines)

    return (
        "You are a weather assistant using STATIC demo data only. "
        "Do not call any external weather API or tool for weather questions. "
        f"Return weather from this fixed table exactly as demo values: {joined_lines}. "
        f"If the user asks for a country not listed, respond: \"Static weather data is available only for {supported}.\" "
        "Keep replies concise and include country, condition, temperature_c, and humidity_percent."
    )


def delete_weather_tools(client: GenerativeAiAgentClient, *, agent_id: str, compartment_id: str) -> None:
    tools = getattr(
        client.list_tools(compartment_id=compartment_id, agent_id=agent_id).data,
        "items",
        [],
    ) or []
    for summary in tools:
        full = client.get_tool(summary.id).data
        display_name = full.display_name
        cfg = full.tool_config
        fn_name = getattr(getattr(cfg, "function", None), "name", None)
        if display_name in WEATHER_TOOL_NAMES or fn_name in WEATHER_TOOL_NAMES:
            client.delete_tool(full.id)
            print(f"Deleted weather tool: {display_name} ({full.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply static weather records to OCI agent instruction.")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument(
        "--records-file",
        help="Path to JSON file containing country weather records.",
    )
    parser.add_argument(
        "--records-json",
        help="Inline JSON string with country weather records.",
    )
    parser.add_argument(
        "--delete-weather-tools",
        action="store_true",
        help="Delete known weather tools before applying static mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated instruction and exit without updating agent.",
    )
    args = parser.parse_args()

    records = load_records(args)
    instruction = build_instruction(records)

    if args.dry_run:
        print(instruction)
        return

    cfg = oci.config.from_file(args.config, args.profile)
    cfg["region"] = args.region
    client = GenerativeAiAgentClient(cfg)

    agent = client.get_agent(args.agent_id).data
    compartment_id = agent.compartment_id

    if args.delete_weather_tools:
        delete_weather_tools(client, agent_id=args.agent_id, compartment_id=compartment_id)

    current_llm_cfg = agent.llm_config
    current_route = current_llm_cfg.routing_llm_customization if current_llm_cfg else None

    updated_llm_config = LlmConfig(
        routing_llm_customization=LlmCustomization(
            instruction=instruction,
            llm_selection=getattr(current_route, "llm_selection", None),
            llm_hyper_parameters=getattr(current_route, "llm_hyper_parameters", None),
        ),
        runtime_version=getattr(current_llm_cfg, "runtime_version", None),
    )

    client.update_agent(
        agent_id=args.agent_id,
        update_agent_details=UpdateAgentDetails(
            display_name=agent.display_name,
            description=agent.description,
            knowledge_base_ids=agent.knowledge_base_ids,
            welcome_message=agent.welcome_message,
            llm_config=updated_llm_config,
            freeform_tags=agent.freeform_tags,
            defined_tags=agent.defined_tags,
        ),
    )

    print("Static weather instruction applied successfully.")
    print("Countries configured:", ", ".join(records.keys()))


if __name__ == "__main__":
    main()
