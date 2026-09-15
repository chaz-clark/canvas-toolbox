# Agent Plugins schema provenance

`plugin.schema.json` is an unchanged copy of the published Agent Plugins 1.0.0 schema:

- canonical id: `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`
- source: <https://github.com/agentplugins/agent-plugins-spec/blob/main/schemas/1.0.0/plugin.schema.json>
- specification: <https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md>
- verified: 2026-09-14

Canvas-specific safety and distribution metadata belongs in the separate Canvas Toolbox package
schemas. Do not add fields to this vendored portable schema. When the upstream specification
changes, add a new versioned directory and test migration explicitly.
