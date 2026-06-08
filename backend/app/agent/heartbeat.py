from __future__ import annotations

import argparse
import asyncio
import os
import socket

import httpx


async def llm_reachable(client: httpx.AsyncClient, base_url: str, *, timeout: float = 5.0) -> bool:
    """Is the local OpenAI-compatible LLM answering? Probes the cheap /models route."""
    try:
        r = await client.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


async def send_heartbeat(
    client: httpx.AsyncClient, vps_url: str, source: str, *, timeout: float = 5.0
) -> bool:
    """POST one heartbeat to the VPS. Returns True on a 200."""
    try:
        r = await client.post(
            f"{vps_url.rstrip('/')}/llm/heartbeat", json={"source": source}, timeout=timeout
        )
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


async def run_once(
    client: httpx.AsyncClient, *, llm_base_url: str, vps_url: str, source: str
) -> bool:
    """One cycle: beat only if the local LLM is reachable. Returns True if a beat was sent."""
    if await llm_reachable(client, llm_base_url):
        return await send_heartbeat(client, vps_url, source)
    return False


async def run_forever(
    *, llm_base_url: str, vps_url: str, source: str, interval: float
) -> None:  # pragma: no cover - long-running loop
    async with httpx.AsyncClient() as client:
        while True:
            await run_once(
                client, llm_base_url=llm_base_url, vps_url=vps_url, source=source
            )
            await asyncio.sleep(interval)


def _parse_args() -> argparse.Namespace:  # pragma: no cover - thin CLI wrapper
    p = argparse.ArgumentParser(description="smistress home-box LLM heartbeat agent")
    p.add_argument("--vps-url", default=os.environ.get("SMISTRESS_VPS_URL", ""))
    p.add_argument(
        "--llm-base-url",
        default=os.environ.get("SMISTRESS_LLM_BASE_URL", "http://localhost:11434/v1"),
    )
    p.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("SMISTRESS_HEARTBEAT_INTERVAL", "30")),
    )
    p.add_argument(
        "--source",
        default=os.environ.get("SMISTRESS_HEARTBEAT_SOURCE", socket.gethostname()),
    )
    return p.parse_args()


def main() -> None:  # pragma: no cover - process entrypoint
    args = _parse_args()
    if not args.vps_url:
        raise SystemExit("set --vps-url or SMISTRESS_VPS_URL (e.g. https://your-vps)")
    asyncio.run(
        run_forever(
            llm_base_url=args.llm_base_url,
            vps_url=args.vps_url,
            source=args.source,
            interval=args.interval,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    main()
