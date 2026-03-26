#!/usr/bin/env python3
"""CLI client that calls OCI GenAI Agent endpoint using ADK function tools."""

from __future__ import annotations

import argparse
import os
import re

from oci.addons.adk import Agent, AgentClient

from oci_agent_weather_tool import (
    DEFAULT_AGENT_ENDPOINT_ID,
    DEFAULT_OCI_CONFIG,
    get_current_weather,
    resolve_agent_endpoint_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a client application that sends user input to an OCI GenAI agent "
            "endpoint with a local weather function tool."
        )
    )
    parser.add_argument(
        "--input",
        help="User message to send to the agent, e.g. 'What is the weather in Chicago?'",
    )
    parser.add_argument(
        "--agent-endpoint-id",
        default=os.getenv("OCI_AGENT_ENDPOINT_ID", DEFAULT_AGENT_ENDPOINT_ID),
        help="Agent endpoint OCID or agent OCID.",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("OCI_PROFILE", "DEFAULT"),
        help="OCI CLI profile.",
    )
    parser.add_argument(
        "--config",
        default=os.getenv("OCI_CONFIG_FILE", DEFAULT_OCI_CONFIG),
        help="Path to OCI config file.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("OCI_REGION"),
        help="OCI region (for example, us-chicago-1).",
    )
    return parser.parse_args()


def infer_region(explicit_region: str | None, agent_or_endpoint_id: str) -> str | None:
    if explicit_region:
        return explicit_region
    match = re.search(r"\.oc1\.([a-z0-9-]+)\.", agent_or_endpoint_id)
    return match.group(1) if match else None


def main() -> None:
    args = parse_args()
    region = infer_region(args.region, args.agent_endpoint_id)
    endpoint_id = resolve_agent_endpoint_id(
        agent_or_endpoint_id=args.agent_endpoint_id,
        config_path=args.config,
        profile=args.profile,
        region=region,
    )

    if endpoint_id != args.agent_endpoint_id:
        print(f"Resolved endpoint OCID: {endpoint_id}")

    client = AgentClient(
        auth_type="api_key",
        config=args.config,
        profile=args.profile,
        region=region,
    )

    agent = Agent(
        client=client,
        agent_endpoint_id=endpoint_id,
        instructions="Perform weather queries using the provided function tool.",
        tools=[get_current_weather],
    )
    agent.setup()

    if args.input:
        response = agent.run(input=args.input)
        response.pretty_print()
        return

    print("Interactive mode. Type your prompt and press Enter (Ctrl+C to exit).")
    while True:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue
        response = agent.run(input=user_input)
        response.pretty_print()


if __name__ == "__main__":
    main()
