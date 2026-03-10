---
inclusion: always
---
# Documentation

There is a hard requirement that the repo and its functionallity is documented well and provides all information for different personas.

## Personas

This section will explain the different personas and their main points of focus. If not needed try to create one documentation for all personas. In case this is not possible provide a highlevel documentation and provide more separated documentation below to address the different personas.

- **Developer** The developer is focused on how the repo can be developed further. Where to find which module and how the architecture is looking like. Also how they can use the `qa-studio` CLI and `SKILL` within their development lifecycle in Kiro, Claude Code or similar tools.
- **QA Engineer** Is interested in how to integrate the tooling into the CI/CD pipeline, how to manage test cases and how to execute them.
- **Business Person** Is interested in understanding the value proposition of the tool. How the tool can be used to create and manage test cases.

## What to document

Depending on the persona different aspects are important. Below is a list with mandatory documentation. In case you're unsure ask if you want to add extra documentation.

- (always) Configuration, at best as a table with defaults and type
- (always) Flags and options for CLI tools as a table with defaults
- (if applicable) User journeys and End user documentation.
- (always) Datamodel as table with data types
- (always) Document eventmessages and their structure

Always make sure that documentation is updated at the end of a coding task.