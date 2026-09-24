# Career Explorer

## How a turn works

1. `CareerExplorerService.send_message` opens a Langfuse trace with **module** `Career Explorer`. The session is `<user id>-career-explorer`.
2. `SectorRelevanceClassifier` reads the message and returns a verdict, a **sector name** and any other sectors the user mentioned.
3. The verdict sets the trace's **sub module**, and the agent routes the turn:

| Sub module | Routed to | Answer source |
|---|---|---|
| `Priority Sector` | `PrioritySectorExplorer` | Vector search over curated sector content |
| `Non Priority Sector` | `NonPrioritySectorExplorer` | Google-grounded search |
| `Sector Classifier Failed` | `NonPrioritySectorExplorer` (fallback) | Google-grounded search. The trace is also tagged `sector_classifier:failed` and scored `sector_classifier_failed` |

## Sector names

- **Priority sectors** come from `CAREER_EXPLORER_CONFIG.sectors` (e.g. Agriculture, Energy, Mining for Zambia). The classifier returns their exact configured names.
- **Non-priority sectors** get a broad industry name, such as `Healthcare` or `Tech/ICT`. Names the user has used before are reused.

Each sector name is saved as a `SectorEngagementEvent` for analytics. Sectors mentioned but not yet discussed are kept as *pending sectors* and brought up in later turns.

## Filtering in Langfuse

Filter by `module:Career Explorer`, then by `sub_module:*`, `treatment_group:*` or the `sector_name` metadata field.
