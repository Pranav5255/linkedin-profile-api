from __future__ import annotations

from linkedin_profile_api.cache.sqlite import CacheStore
from linkedin_profile_api.linkedin.endpoints import CapturedEndpoints, OperationSpec


class QueryRegistry:
    def __init__(self, cache: CacheStore, captured: CapturedEndpoints) -> None:
        self._cache = cache
        self._captured = captured

    def reload_captured(self, captured: CapturedEndpoints) -> None:
        self._captured = captured

    async def seed_from_captured(self) -> None:
        for name, spec in self._captured.operations.items():
            if spec.query_id or spec.decoration_id:
                await self._cache.upsert_query(
                    name,
                    spec.query_id,
                    spec.decoration_id,
                    source_asset=self._captured.source_har,
                )

    async def resolve(self, operation_name: str) -> OperationSpec:
        captured = self._captured.operation(operation_name)
        stored = await self._cache.get_query(operation_name)
        spec = captured or OperationSpec(name=operation_name, path="/voyager/api/graphql")
        if stored:
            spec.query_id = stored.get("query_id") or spec.query_id
            spec.decoration_id = stored.get("decoration_id") or spec.decoration_id
        return spec

    async def remember(
        self,
        operation_name: str,
        query_id: str | None,
        decoration_id: str | None,
        source_asset: str | None,
        *,
        mark_success: bool = False,
    ) -> None:
        await self._cache.upsert_query(
            operation_name,
            query_id,
            decoration_id,
            source_asset,
            mark_success=mark_success,
        )

    async def invalidate(self, operation_name: str) -> None:
        await self._cache.invalidate_query(operation_name)
