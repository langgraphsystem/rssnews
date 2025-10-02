"""Unit tests for GraphBuilder"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from core.graph.graph_builder import GraphBuilder, create_graph_builder


@pytest.fixture
def sample_docs():
    """Sample documents for graph building"""
    return [
        {
            "article_id": "doc1",
            "title": "OpenAI Releases GPT-5",
            "snippet": "OpenAI announced GPT-5 today. Sam Altman spoke at the conference.",
            "date": "2025-01-15",
            "url": "https://techcrunch.com/gpt5"
        },
        {
            "article_id": "doc2",
            "title": "Google Launches Gemini Pro",
            "snippet": "Google unveiled Gemini Pro. Sundar Pichai presented the features.",
            "date": "2025-01-14",
            "url": "https://wired.com/gemini"
        },
        {
            "article_id": "doc3",
            "title": "Microsoft Partners with OpenAI",
            "snippet": "Microsoft and OpenAI announced partnership. Satya Nadella commented.",
            "date": "2025-01-13",
            "url": "https://bloomberg.com/msft"
        }
    ]


@pytest.fixture
def graph_builder():
    """Create GraphBuilder instance"""
    return create_graph_builder()


class TestGraphBuilder:
    """Test suite for GraphBuilder"""

    @pytest.mark.asyncio
    async def test_build_graph_basic(self, graph_builder, sample_docs):
        """Test basic graph construction"""
        graph = await graph_builder.build_graph(
            docs=sample_docs,
            max_nodes=100,
            max_edges=200,
            lang="en"
        )

        assert "nodes" in graph
        assert "edges" in graph
        assert "metadata" in graph
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) >= 0

    @pytest.mark.asyncio
    async def test_extract_entities(self, graph_builder, sample_docs):
        """Test entity extraction"""
        entities = await graph_builder._extract_entities(sample_docs, lang="en")

        # Should extract: OpenAI, GPT, Sam Altman, Google, Gemini, etc.
        assert len(entities) > 0

        entity_names = [e["name"] for e in entities]
        assert any("OpenAI" in name for name in entity_names)
        assert any("Google" in name for name in entity_names)

    def test_guess_entity_type(self, graph_builder):
        """Test entity type guessing"""
        assert graph_builder._guess_entity_type("OpenAI Inc") == "organization"
        assert graph_builder._guess_entity_type("Google") == "organization"
        assert graph_builder._guess_entity_type("Sam Altman") in ["person", "entity"]
        assert graph_builder._guess_entity_type("University") == "organization"

    @pytest.mark.asyncio
    async def test_extract_relations(self, graph_builder, sample_docs):
        """Test relation extraction"""
        entities = await graph_builder._extract_entities(sample_docs, lang="en")
        relations = await graph_builder._extract_relations(sample_docs, entities, lang="en")

        assert len(relations) >= 0

        # Relations should have required fields
        for rel in relations:
            assert "src" in rel
            assert "tgt" in rel
            assert "type" in rel
            assert "weight" in rel
            assert 0.0 <= rel["weight"] <= 1.0

    def test_infer_relation_type(self, graph_builder):
        """Test relation type inference"""
        ent1 = {"name": "OpenAI", "type": "organization"}
        ent2 = {"name": "Microsoft", "type": "organization"}

        # Test different contexts
        rel_type = graph_builder._infer_relation_type(
            ent1, ent2, "microsoft invests in openai"
        )
        assert rel_type == "influences"

        rel_type = graph_builder._infer_relation_type(
            ent1, ent2, "microsoft partners with openai"
        )
        assert rel_type == "relates_to"

    @pytest.mark.asyncio
    async def test_construct_graph(self, graph_builder, sample_docs):
        """Test graph structure construction"""
        entities = await graph_builder._extract_entities(sample_docs, lang="en")
        relations = await graph_builder._extract_relations(sample_docs, entities, lang="en")

        nodes, edges = graph_builder._construct_graph(
            entities=entities,
            relations=relations,
            docs=sample_docs,
            max_nodes=50,
            max_edges=100
        )

        # Check nodes
        assert len(nodes) > 0
        assert len(nodes) <= 50

        for node in nodes:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert node["type"] in ["entity", "article"]

        # Check edges
        assert len(edges) <= 100

        for edge in edges:
            assert "src" in edge
            assert "tgt" in edge
            assert "type" in edge
            assert "weight" in edge

    @pytest.mark.asyncio
    async def test_build_graph_respects_limits(self, graph_builder, sample_docs):
        """Test that graph respects max_nodes and max_edges limits"""
        # Create more docs to test limits
        many_docs = sample_docs * 50  # 150 docs

        graph = await graph_builder.build_graph(
            docs=many_docs,
            max_nodes=20,
            max_edges=30,
            lang="en"
        )

        assert len(graph["nodes"]) <= 20
        assert len(graph["edges"]) <= 30

    @pytest.mark.asyncio
    async def test_build_graph_empty_docs(self, graph_builder):
        """Test graph building with empty documents"""
        graph = await graph_builder.build_graph(
            docs=[],
            max_nodes=100,
            max_edges=200,
            lang="en"
        )

        assert len(graph["nodes"]) == 0
        assert len(graph["edges"]) == 0

    @pytest.mark.asyncio
    async def test_build_graph_metadata(self, graph_builder, sample_docs):
        """Test graph metadata"""
        graph = await graph_builder.build_graph(
            docs=sample_docs,
            max_nodes=100,
            max_edges=200,
            lang="en"
        )

        metadata = graph["metadata"]
        assert "source_docs" in metadata
        assert "entities_extracted" in metadata
        assert "relations_extracted" in metadata
        assert "nodes_final" in metadata
        assert "edges_final" in metadata

        assert metadata["source_docs"] == len(sample_docs)


@pytest.mark.asyncio
async def test_graph_builder_with_special_characters(graph_builder):
    """Test graph building with special characters"""
    docs = [
        {
            "article_id": "doc1",
            "title": "AI (Artificial Intelligence) & ML",
            "snippet": "AI/ML technologies: OpenAI, Google's Gemini",
            "date": "2025-01-15"
        }
    ]

    graph = await graph_builder.build_graph(docs, max_nodes=50, max_edges=100, lang="en")

    # Should handle special characters gracefully
    assert len(graph["nodes"]) > 0
