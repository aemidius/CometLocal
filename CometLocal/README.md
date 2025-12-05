# CometLocal

Proyecto base tipo Comet local.

## Goal Decomposer v1

This version introduces a deterministic and fully local goal decomposition system.

Key characteristics:

- Compound goals are split into ordered sub-goals without using LLMs

- Each sub-goal is executed in its own isolated browser context

- Wikipedia goals always resolve to final article pages

- Searches never remain in Special:Search results

- All steps are annotated with sub_goal_index and focus_entity

- Fully backward compatible with existing backend endpoints

Example supported goal:

"investiga quién fue Ada Lovelace y luego mira información sobre Charles Babbage en Wikipedia"

Expected behavior:

- Each entity is handled independently

- Final answers are numbered and sourced from Wikipedia articles only
