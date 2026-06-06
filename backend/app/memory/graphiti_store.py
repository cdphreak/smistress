from __future__ import annotations

from datetime import datetime

from app.config import Settings


class GraphitiMemoryStore:
    """Graphiti/FalkorDB adapter (spec 3). Imports graphiti-core lazily so the heavy
    dependency only loads when graphiti is actually enabled."""

    def __init__(self, settings: Settings) -> None:
        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.nodes import EpisodeType

        self._episode_types = {
            "text": EpisodeType.text,
            "json": EpisodeType.json,
            "message": EpisodeType.message,
        }

        driver = FalkorDriver(
            host=settings.falkordb_host, port=str(settings.falkordb_port)
        )
        llm_config = LLMConfig(
            api_key=settings.llm_api_key,
            model=settings.chat_model,
            small_model=settings.chat_model,
            base_url=settings.llm_base_url,
        )
        llm_client = OpenAIGenericClient(config=llm_config)
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=settings.llm_api_key,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                base_url=settings.llm_base_url,
            )
        )
        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=OpenAIRerankerClient(client=llm_client, config=llm_config),
        )
        self._indices_ready = False

    async def _ensure_indices(self) -> None:
        if not self._indices_ready:
            await self._graphiti.build_indices_and_constraints()
            self._indices_ready = True

    async def add_episode(
        self,
        *,
        group_id: str,
        name: str,
        body: str,
        source: str,
        source_description: str,
        reference_time: datetime,
    ) -> None:
        await self._ensure_indices()
        await self._graphiti.add_episode(
            name=name,
            episode_body=body,
            source=self._episode_types.get(source, self._episode_types["text"]),
            source_description=source_description,
            reference_time=reference_time,
            group_id=group_id,
        )

    async def retrieve(self, *, group_id: str, query: str, num_results: int = 10) -> str:
        results = await self._graphiti.search(
            query=query, group_ids=[group_id], num_results=num_results
        )
        return "\n".join(f"- {r.fact}" for r in results)
