# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Coalesce concurrent Embedding requests and cache successful vectors."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from typing import Any

from powercontext.builtin.inference import EmbeddingResult, InferenceUsage


class CoalescingEmbeddingModel:
    """Share in-flight Embedding work between callers and cache its vectors."""

    def __init__(
        self,
        model: Any,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")  # noqa: TRY003
        if coalesce_ms < 0:
            raise ValueError("coalesce_ms must not be negative")  # noqa: TRY003
        if cache_size < 0:
            raise ValueError("cache_size must not be negative")  # noqa: TRY003
        self._model = model
        self.profile = model.profile
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = coalesce_ms / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[tuple[Any, int | None]]] = {}
        self._queue: deque[str] = deque()
        self._batch_usage: dict[int, InferenceUsage] = {}
        self._batch_seq = 0
        self._flusher: asyncio.Task[None] | None = None

    async def embed(self, texts: Any) -> EmbeddingResult:
        inputs = tuple(texts)
        if not inputs:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        unique = tuple(dict.fromkeys(inputs))
        waits: dict[str, asyncio.Future[tuple[Any, int | None]] | None] = {}
        for text in unique:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                waits[text] = None
            elif text in self._inflight:
                waits[text] = self._inflight[text]
            else:
                future: asyncio.Future[tuple[Any, int | None]] = asyncio.get_running_loop().create_future()
                self._inflight[text] = future
                waits[text] = future
                self._queue.append(text)
                self._ensure_flusher()

        vectors: dict[str, Any] = {}
        batch_ids: set[int] = set()
        for text, future in waits.items():
            if future is None:
                vectors[text] = self._cache[text]
            else:
                vector, batch_id = await asyncio.shield(future)
                vectors[text] = vector
                if batch_id is not None:
                    batch_ids.add(batch_id)

        usage = _merge_usage([self._batch_usage[batch_id] for batch_id in batch_ids])
        return EmbeddingResult(vectors=tuple(vectors[text] for text in inputs), usage=usage)

    def _ensure_flusher(self) -> None:
        if self._flusher is None or self._flusher.done():
            self._flusher = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        try:
            while self._queue:
                if self._coalesce_seconds > 0:
                    await asyncio.sleep(self._coalesce_seconds)
                else:
                    await asyncio.sleep(0)
                batch: list[str] = []
                while self._queue and len(batch) < self._max_batch_size:
                    batch.append(self._queue.popleft())
                if batch:
                    await self._run_batch(batch)
        finally:
            self._flusher = None
            if self._queue:
                self._ensure_flusher()

    async def _run_batch(self, batch: list[str]) -> None:
        self._batch_seq += 1
        batch_id = self._batch_seq
        try:
            result = await self._model.embed(tuple(batch))
            if len(result.vectors) != len(batch):
                raise ValueError("embedding vector count does not match the batch size")  # noqa: TRY003
            self._batch_usage[batch_id] = result.usage
            for text, vector in zip(batch, result.vectors, strict=True):
                self._store(text, vector)
                self._resolve(text, (vector, batch_id))
        except BaseException as exc:  # noqa: BLE001 - propagate the provider failure to every waiter
            for text in batch:
                self._reject(text, exc)
            raise

    def _resolve(self, text: str, value: tuple[Any, int | None]) -> None:
        future = self._inflight.pop(text, None)
        if future is not None and not future.done():
            future.set_result(value)

    def _reject(self, text: str, exc: BaseException) -> None:
        future = self._inflight.pop(text, None)
        if future is not None and not future.done():
            future.set_exception(exc)
            future.exception()

    def _store(self, text: str, vector: Any) -> None:
        if self._cache_size <= 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


def _merge_usage(usages: list[InferenceUsage]) -> InferenceUsage:
    if not usages:
        return InferenceUsage(requests=0)
    input_tokens = _sum_optional(usage.input_tokens for usage in usages)
    output_tokens = _sum_optional(usage.output_tokens for usage in usages)
    return InferenceUsage(
        requests=sum(usage.requests for usage in usages),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _sum_optional(values: Any) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


__all__ = ["CoalescingEmbeddingModel"]
