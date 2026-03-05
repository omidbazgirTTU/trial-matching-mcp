# Trial Matching MCP Server

Agent that wraps the remote Medical Research MCP to surface alternate-therapy trials for the
"Alternate Therapy Evaluation" subcohort.

## Tools

- `list_trial_patients` – synthetic cards for three patients needing trial evaluation (returns an
  MCP App widget URI for quick visualization).
- `match_patient_trials` – calls the Medical Research MCP (`search_trials`) to fetch recruiting
  Phase 2/3 trials, filters by mechanism exclusions, and returns coordinator-ready match cards.
- `trial_matching_summary` – high-level dataset/persona snapshot.

## Local setup

```bash
cd trial-matching-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m trial_matching_mcp_server.server --transport http --host 127.0.0.1 --port 8020
```

Test with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector --http http://127.0.0.1:8020/mcp
```

## Deploy to Vercel

```bash
cd trial-matching-mcp-server
vercel
vercel deploy --prod
```

Hit the hosted function at `https://<deployment>.vercel.app/api/mcp.py` (SSE JSON-RPC just like the
other MCP servers) and call `match_patient_trials` via Inspector or curl.
