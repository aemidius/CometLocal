# CometLocal

Proyecto base tipo Comet local.

## 🚀 Inicio Rápido (5 minutos)

**¿Primera vez?** Sigue el [**Onboarding**](docs/ONBOARDING.md) para probar CometLocal en modo demo sin configurar datos reales.

```bash
# Arrancar en modo DEMO
set ENVIRONMENT=demo  # Windows
# export ENVIRONMENT=demo  # Linux/Mac
python -m uvicorn backend.app:app --reload
```

Abre: **http://127.0.0.1:8000/repository_v3.html**

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
