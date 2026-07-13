#!/usr/bin/env python3
"""
Migrate a canvas-toolbox agent from MD+JSON to MD+YAML frontmatter.

Usage:
    python _migrate_agent_to_yaml.py canvas_course_expert
"""

import json
import sys
import yaml
from pathlib import Path


def migrate_agent(agent_name: str):
    """Migrate agent from MD+JSON to MD+YAML frontmatter."""

    agents_dir = Path(__file__).parent.parent / "agents"
    json_path = agents_dir / f"{agent_name}.json"
    md_path = agents_dir / f"{agent_name}.md"

    if not json_path.exists():
        print(f"ERROR: {json_path} not found")
        return False

    if not md_path.exists():
        print(f"ERROR: {md_path} not found")
        return False

    # Load JSON
    with open(json_path) as f:
        json_data = json.load(f)

    # Load existing markdown
    md_content = md_path.read_text(encoding="utf-8")

    # Extract metadata from JSON
    metadata = json_data.get("_metadata", {})
    agent_details = metadata.get("agent_details", {})

    # Build YAML frontmatter
    frontmatter = {
        "name": agent_name,
        "version": agent_details.get("version", "3.1"),
        "last_updated": agent_details.get("last_updated", metadata.get("last_updated", "2026-07-07")),
        "description": agent_details.get("description", metadata.get("description", "")),
        "complexity": agent_details.get("complexity", "standard"),
        "agent_type": json_data.get("agent_type", {}).get("type", "workflow"),
    }

    # Add runtime_data marker if this agent has primary_data
    if "primary_data" in json_data:
        frontmatter["runtime_data"] = {
            "audit_rules": "see_runtime_configuration",
            "byui_standards": "see_runtime_configuration",
        }

    # Add llm_agent marker if this agent has implementation.llm_agent
    if "implementation" in json_data and "llm_agent" in json_data["implementation"]:
        frontmatter["runtime_data"] = frontmatter.get("runtime_data", {})
        frontmatter["runtime_data"]["llm_config"] = "see_runtime_configuration"

    # Build new markdown content
    new_md = "---\n"
    new_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    new_md += "---\n\n"
    new_md += md_content

    # Add runtime configuration section if needed
    if "primary_data" in json_data or ("implementation" in json_data and "llm_agent" in json_data["implementation"]):
        new_md += "\n\n---\n\n"
        new_md += "## Runtime Configuration\n\n"
        new_md += "_This section contains structured data used by `canvas_api_tool.py` at runtime._\n\n"

        # Add audit_rules if present
        if "primary_data" in json_data and "audit_rules" in json_data["primary_data"]:
            new_md += "### Audit Rules\n\n"
            new_md += "```yaml\n"
            new_md += yaml.dump({"audit_rules": json_data["primary_data"]["audit_rules"]}, default_flow_style=False, sort_keys=False)
            new_md += "```\n\n"

        # Add byui_standards if present
        if "primary_data" in json_data and "byui_standards" in json_data["primary_data"]:
            new_md += "### BYUI Standards\n\n"
            new_md += "```yaml\n"
            new_md += yaml.dump({"byui_standards": json_data["primary_data"]["byui_standards"]}, default_flow_style=False, sort_keys=False)
            new_md += "```\n\n"

        # Add llm_agent config if present
        if "implementation" in json_data and "llm_agent" in json_data["implementation"]:
            new_md += "### LLM Agent Configuration\n\n"
            new_md += "```yaml\n"
            new_md += yaml.dump({"llm_agent": json_data["implementation"]["llm_agent"]}, default_flow_style=False, sort_keys=False, width=120)
            new_md += "```\n"

    # Write new markdown
    output_path = md_path.with_suffix(".yaml.md")
    output_path.write_text(new_md, encoding="utf-8")

    print(f"✅ Migrated {agent_name}")
    print(f"   Input:  {json_path} ({json_path.stat().st_size} bytes)")
    print(f"   Input:  {md_path} ({md_path.stat().st_size} bytes)")
    print(f"   Output: {output_path} ({output_path.stat().st_size} bytes)")
    print(f"\n   Review the output, then run:")
    print(f"   mv {output_path} {md_path}")

    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python _migrate_agent_to_yaml.py <agent_name>")
        print("Example: python _migrate_agent_to_yaml.py canvas_course_expert")
        sys.exit(1)

    agent_name = sys.argv[1]
    success = migrate_agent(agent_name)
    sys.exit(0 if success else 1)
