"""Basic HelloAGI Agent — Simplest possible usage.

Shows how to create an agent and interact with it programmatically.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agi_runtime.core.agent import HelloAGIAgent

# Create agent with default settings
agent = HelloAGIAgent()

# Show agent identity
print(f"Agent: {agent.identity.state.name}")
print(f"Character: {agent.identity.state.character}")
print(f"Tools: {len(agent.tool_registry.list_tools())} available")
print()

# Single interaction
response = agent.think("What tools do you have available?")
print(f"Decision: {response.decision} | Risk: {response.risk}")
print(f"Response: {response.text}")
