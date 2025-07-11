# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from llama_stack.apis.vector_dbs import VectorDB
from llama_stack.apis.vector_io import (
    QueryChunksResponse,
    VectorStoreDeleteResponse,
    VectorStoreListResponse,
    VectorStoreObject,
    VectorStoreSearchResponse,
)

logger = logging.getLogger(__name__)

# Constants for OpenAI vector stores
CHUNK_MULTIPLIER = 5


class OpenAIVectorStoreMixin(ABC):
    """
    Mixin class that provides common OpenAI Vector Store API implementation.
    Providers need to implement the abstract storage methods and maintain
    an openai_vector_stores in-memory cache.
    """

    # These should be provided by the implementing class
    openai_vector_stores: dict[str, dict[str, Any]]

    @abstractmethod
    async def _save_openai_vector_store(self, store_id: str, store_info: dict[str, Any]) -> None:
        """Save vector store metadata to persistent storage."""
        pass

    @abstractmethod
    async def _load_openai_vector_stores(self) -> dict[str, dict[str, Any]]:
        """Load all vector store metadata from persistent storage."""
        pass

    @abstractmethod
    async def _update_openai_vector_store(self, store_id: str, store_info: dict[str, Any]) -> None:
        """Update vector store metadata in persistent storage."""
        pass

    @abstractmethod
    async def _delete_openai_vector_store_from_storage(self, store_id: str) -> None:
        """Delete vector store metadata from persistent storage."""
        pass

    @abstractmethod
    async def register_vector_db(self, vector_db: VectorDB) -> None:
        """Register a vector database (provider-specific implementation)."""
        pass

    @abstractmethod
    async def unregister_vector_db(self, vector_db_id: str) -> None:
        """Unregister a vector database (provider-specific implementation)."""
        pass

    @abstractmethod
    async def query_chunks(
        self, vector_db_id: str, query: Any, params: dict[str, Any] | None = None
    ) -> QueryChunksResponse:
        """Query chunks from a vector database (provider-specific implementation)."""
        pass

    async def openai_create_vector_store(
        self,
        name: str,
        file_ids: list[str] | None = None,
        expires_after: dict[str, Any] | None = None,
        chunking_strategy: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_model: str | None = None,
        embedding_dimension: int | None = 384,
        provider_id: str | None = None,
        provider_vector_db_id: str | None = None,
    ) -> VectorStoreObject:
        """Creates a vector store."""
        print("IN OPENAI VECTOR STORE MIXIN, openai_create_vector_store")
        # store and vector_db have the same id
        store_id = name or str(uuid.uuid4())
        created_at = int(time.time())

        if provider_id is None:
            raise ValueError("Provider ID is required")

        if embedding_model is None:
            raise ValueError("Embedding model is required")

        # Use provided embedding dimension or default to 384
        if embedding_dimension is None:
            raise ValueError("Embedding dimension is required")

        provider_vector_db_id = provider_vector_db_id or store_id
        vector_db = VectorDB(
            identifier=store_id,
            embedding_dimension=embedding_dimension,
            embedding_model=embedding_model,
            provider_id=provider_id,
            provider_resource_id=provider_vector_db_id,
        )
        from rich.pretty import pprint

        print("VECTOR DB")
        pprint(vector_db)

        # Register the vector DB
        await self.register_vector_db(vector_db)

        # Create OpenAI vector store metadata
        store_info = {
            "id": store_id,
            "object": "vector_store",
            "created_at": created_at,
            "name": store_id,
            "usage_bytes": 0,
            "file_counts": {},
            "status": "completed",
            "expires_after": expires_after,
            "expires_at": None,
            "last_active_at": created_at,
            "file_ids": file_ids or [],
            "chunking_strategy": chunking_strategy,
        }

        # Add provider information to metadata if provided
        metadata = metadata or {}
        if provider_id:
            metadata["provider_id"] = provider_id
        if provider_vector_db_id:
            metadata["provider_vector_db_id"] = provider_vector_db_id
        store_info["metadata"] = metadata

        # Save to persistent storage (provider-specific)
        await self._save_openai_vector_store(store_id, store_info)

        # Store in memory cache
        self.openai_vector_stores[store_id] = store_info

        return VectorStoreObject(
            id=store_id,
            created_at=created_at,
            name=store_id,
            usage_bytes=0,
            file_counts={},
            status="completed",
            expires_after=expires_after,
            expires_at=None,
            last_active_at=created_at,
            metadata=metadata,
        )

    async def openai_list_vector_stores(
        self,
        limit: int | None = 20,
        order: str | None = "desc",
        after: str | None = None,
        before: str | None = None,
    ) -> VectorStoreListResponse:
        """Returns a list of vector stores."""
        limit = limit or 20
        order = order or "desc"

        # Get all vector stores
        all_stores = list(self.openai_vector_stores.values())

        # Sort by created_at
        reverse_order = order == "desc"
        all_stores.sort(key=lambda x: x["created_at"], reverse=reverse_order)

        # Apply cursor-based pagination
        if after:
            after_index = next((i for i, store in enumerate(all_stores) if store["id"] == after), -1)
            if after_index >= 0:
                all_stores = all_stores[after_index + 1 :]

        if before:
            before_index = next((i for i, store in enumerate(all_stores) if store["id"] == before), len(all_stores))
            all_stores = all_stores[:before_index]

        # Apply limit
        limited_stores = all_stores[:limit]
        # Convert to VectorStoreObject instances
        data = [VectorStoreObject(**store) for store in limited_stores]

        # Determine pagination info
        has_more = len(all_stores) > limit
        first_id = data[0].id if data else None
        last_id = data[-1].id if data else None

        return VectorStoreListResponse(
            data=data,
            has_more=has_more,
            first_id=first_id,
            last_id=last_id,
        )

    async def openai_retrieve_vector_store(
        self,
        vector_store_id: str,
    ) -> VectorStoreObject:
        """Retrieves a vector store."""
        if vector_store_id not in self.openai_vector_stores:
            raise ValueError(f"Vector store {vector_store_id} not found")

        store_info = self.openai_vector_stores[vector_store_id]
        return VectorStoreObject(**store_info)

    async def openai_update_vector_store(
        self,
        vector_store_id: str,
        name: str | None = None,
        expires_after: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VectorStoreObject:
        """Modifies a vector store."""
        if vector_store_id not in self.openai_vector_stores:
            raise ValueError(f"Vector store {vector_store_id} not found")

        store_info = self.openai_vector_stores[vector_store_id].copy()

        # Update fields if provided
        if name is not None:
            store_info["name"] = name
        if expires_after is not None:
            store_info["expires_after"] = expires_after
        if metadata is not None:
            store_info["metadata"] = metadata

        # Update last_active_at
        store_info["last_active_at"] = int(time.time())

        # Save to persistent storage (provider-specific)
        await self._update_openai_vector_store(vector_store_id, store_info)

        # Update in-memory cache
        self.openai_vector_stores[vector_store_id] = store_info

        return VectorStoreObject(**store_info)

    async def openai_delete_vector_store(
        self,
        vector_store_id: str,
    ) -> VectorStoreDeleteResponse:
        """Delete a vector store."""
        if vector_store_id not in self.openai_vector_stores:
            raise ValueError(f"Vector store {vector_store_id} not found")

        # Delete from persistent storage (provider-specific)
        await self._delete_openai_vector_store_from_storage(vector_store_id)

        # Delete from in-memory cache
        del self.openai_vector_stores[vector_store_id]

        # Also delete the underlying vector DB
        try:
            await self.unregister_vector_db(vector_store_id)
        except Exception as e:
            logger.warning(f"Failed to delete underlying vector DB {vector_store_id}: {e}")

        return VectorStoreDeleteResponse(
            id=vector_store_id,
            deleted=True,
        )

    async def openai_search_vector_store(
        self,
        vector_store_id: str,
        query: str | list[str],
        filters: dict[str, Any] | None = None,
        max_num_results: int | None = 10,
        ranking_options: dict[str, Any] | None = None,
        rewrite_query: bool | None = False,
        # search_mode: Literal["keyword", "vector", "hybrid"] = "vector",
    ) -> VectorStoreSearchResponse:
        """Search for chunks in a vector store."""
        # TODO: Add support in the API for this
        search_mode = "vector"
        max_num_results = max_num_results or 10

        if vector_store_id not in self.openai_vector_stores:
            raise ValueError(f"Vector store {vector_store_id} not found")

        if isinstance(query, list):
            search_query = " ".join(query)
        else:
            search_query = query

        try:
            score_threshold = ranking_options.get("score_threshold", 0.0) if ranking_options else 0.0
            params = {
                "max_chunks": max_num_results * CHUNK_MULTIPLIER,
                "score_threshold": score_threshold,
                "mode": search_mode,
            }
            # TODO: Add support for ranking_options.ranker

            response = await self.query_chunks(
                vector_db_id=vector_store_id,
                query=search_query,
                params=params,
            )

            # Convert response to OpenAI format
            data = []
            for i, (chunk, score) in enumerate(zip(response.chunks, response.scores, strict=False)):
                # Apply score based filtering
                if score < score_threshold:
                    continue

                # Apply filters if provided
                if filters:
                    # Simple metadata filtering
                    if not self._matches_filters(chunk.metadata, filters):
                        continue

                chunk_data = {
                    "id": f"chunk_{i}",
                    "object": "vector_store.search_result",
                    "score": score,
                    "content": chunk.content.content if hasattr(chunk.content, "content") else str(chunk.content),
                    "metadata": chunk.metadata,
                }
                data.append(chunk_data)
                if len(data) >= max_num_results:
                    break

            return VectorStoreSearchResponse(
                search_query=search_query,
                data=data,
                has_more=False,  # For simplicity, we don't implement pagination here
                next_page=None,
            )

        except Exception as e:
            logger.error(f"Error searching vector store {vector_store_id}: {e}")
            # Return empty results on error
            return VectorStoreSearchResponse(
                search_query=search_query,
                data=[],
                has_more=False,
                next_page=None,
            )

    def _matches_filters(self, metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Check if metadata matches the provided filters."""
        for key, value in filters.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True
