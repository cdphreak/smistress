# Home-box heartbeat agent

Runs on the home GPU machine. While the local OpenAI-compatible LLM (Ollama/vLLM/etc.)
answers `GET {llm_base_url}/models`, it POSTs a heartbeat to the VPS so the app knows the
Mistress is reachable (Addendum B2). The box always initiates the connection, so it works
behind NAT / a dynamic IP — the VPS never reaches inward.

## Run

```bash
# from backend/ (needs only httpx, already in the project deps)
SMISTRESS_VPS_URL=https://your-vps \
SMISTRESS_LLM_BASE_URL=http://localhost:11434/v1 \
SMISTRESS_HEARTBEAT_INTERVAL=30 \
uv run python -m app.agent.heartbeat
```

The VPS marks the LLM `online` while heartbeats arrive and `offline` once they are older
than `SMISTRESS_HEARTBEAT_TTL_SECONDS` (default 90s) — keep the interval well under the TTL
so a single missed beat doesn't flip the state.
