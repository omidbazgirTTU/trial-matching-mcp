# Trial Matching MCP Server

This MCP server helps research coordinators surface alternate-therapy trials for the **“Alternate Therapy Evaluation”** subcohort.  
It stitches together:

- The Oracle Medical Research MCP (for live trial search, trial details, eligibility, and enrollment counts).
- The Homecare Cohort MCP (for patient-level context such as risk tier, lab trends, and ZIP codes).
- Custom UI widgets rendered through the `io.modelcontextprotocol/ui` extension (patient queue, match cards, shortlist tables, etc.).

## Available tools & sample prompts

| Tool | What it does | Example prompt that triggers it |
| --- | --- | --- |
| `list_trial_patients` | Returns synthetic queue of patients needing trial review (with MCP widget). | “Show me the patients currently flagged for alternate-therapy trials.” |
| `match_patient_trials` | Calls the Medical Research MCP to fetch Phase 2/3 recruiting trials, filters out duplicate mechanisms, and returns match cards. | “Find live trials for patient ALT-TRIAL-001 that exclude SGLT2 mechanisms.” |
| `trial_matching_summary` | Snapshot of persona, as-of date, and cohort size (with UI widget). | “Give me a quick overview of this trial-matching dataset.” |
| `generate_recruitment_shortlist` | Builds a ranked shortlist across patients, blending eligibility signals, mechanism novelty, real ZIP distances, and nearest sites. | “Generate a recruitment shortlist for all flagged patients, ranked by eligibility probability.” |
| `get_trial_brief` | Pulls trial details + eligibility text for a specific NCT ID. | “Summarize trial NCT01234567 so I can brief the cardiology coordinator.” |
| `analyze_trial_eligibility` | Compares a patient profile against a trial’s eligibility text and highlights attention items. | “Does ALT-TRIAL-002 meet the eligibility for NCT01234567? Call out any gaps.” |
| `geospatial_coverage` | Shows nearest recruiting sites and bucketed distances for each patient. | “Where are the closest trial sites for ALT-TRIAL-003, and how far are they?” |
| `enrollment_signals` | Uses Medical Research MCP counts/search to report recruiting vs completed trial volumes for a condition. | “What’s the current enrollment signal for uncontrolled T2D trials?” |
| `log_follow_up` | Records an action item (stored in `coordinator_followups.json`). | “Create a follow-up note for ALT-TRIAL-001 to call Emory Midtown by Friday.” |
| `list_follow_up_items` | Lists stored follow-up entries, optionally filtered by patient. | “Show all open follow-ups for ALT-TRIAL-001.” |

## Local setup

```bash
cd trial-matching-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Run the MCP server over HTTP
python -m trial_matching_mcp_server.server --host 127.0.0.1 --port 8020
```

### Inspect locally with MCP Inspector

In a second terminal:

```bash
cd /Users/<you>/Desktop/Project/TopGun/trial-matching-mcp-server
npx @modelcontextprotocol/inspector --transport http --server-url http://127.0.0.1:8020/mcp
```

If the proxy/UI ports (6277/6274) are “in use,” stop any previous Inspector processes first:

```bash
lsof -i tcp:6277 -i tcp:6274
kill <pid>
```

## Deployment (Vercel)

```bash
cd trial-matching-mcp-server
vercel            # first-time link to a project
vercel deploy --prod
```

The production endpoint is exposed at:

```
https://trial-matching-mcp-server.vercel.app/mcp
```

(Legacy `/api/mcp.py` still works via rewrite, but the cleaner `/mcp` path is the canonical URL to use with MCP Inspector or ChatGPT.)

## Notes & integration details

- `requirements.txt` includes `fastmcp`, `httpx`, and `pgeocode` (used to translate patient ZIP codes into approximate drive distances).
- `patients.json` links the synthetic patients to their corresponding Homecare cohort IDs (`homecare_patient_id`) so we can fetch live ZIP codes and risk context.
- Cached homecare profiles live in `trial_matching_mcp_server/homecare_patients_cache.json` and refresh hourly to minimize remote calls.
- UI widgets are defined under `widgets/` and registered automatically via `ui.py`; any tool response that includes a `ui` object surfaces in MCP-compatible clients (ChatGPT MCP apps, Inspector, etc.).
