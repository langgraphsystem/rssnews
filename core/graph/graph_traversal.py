"""
Graph Traversal — Multi-hop traversal and subgraph extraction for GraphRAG.
Supports BFS/DFS traversal with hop limits and path finding.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class GraphTraversal:
    """Handles graph traversal and subgraph extraction"""

    def __init__(self, graph: Dict[str, Any]):
        """
        Initialize with graph structure

        Args:
            graph: Graph dict with "nodes" and "edges"
        """
        self.graph = graph
        self.nodes = {n["id"]: n for n in graph.get("nodes", [])}
        self.edges = graph.get("edges", [])

        # Build adjacency list
        self.adj_list = self._build_adjacency_list()

    def _build_adjacency_list(self) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
        """Build adjacency list from edges"""
        adj = defaultdict(list)

        for edge in self.edges:
            src = edge["src"]
            tgt = edge["tgt"]
            adj[src].append((tgt, edge))
            # Undirected graph
            adj[tgt].append((src, edge))

        return dict(adj)

    def traverse_bfs(
        self,
        start_nodes: List[str],
        hop_limit: int = 3,
        max_nodes: int = 50
    ) -> Dict[str, Any]:
        """
        BFS traversal from start nodes

        Args:
            start_nodes: Node IDs to start from
            hop_limit: Maximum number of hops
            max_nodes: Maximum nodes to visit

        Returns:
            Subgraph dict
        """
        visited: Set[str] = set()
        queue = deque()

        # Initialize queue with start nodes
        for node_id in start_nodes:
            if node_id in self.nodes:
                queue.append((node_id, 0))  # (node_id, hop_count)
                visited.add(node_id)

        subgraph_nodes = []
        subgraph_edges = []

        while queue and len(visited) < max_nodes:
            node_id, hops = queue.popleft()

            # Add node to subgraph
            if node_id in self.nodes:
                subgraph_nodes.append(self.nodes[node_id])

            # Stop if reached hop limit
            if hops >= hop_limit:
                continue

            # Explore neighbors
            for neighbor_id, edge in self.adj_list.get(node_id, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, hops + 1))

                    # Add edge to subgraph
                    if len(subgraph_edges) < max_nodes * 2:  # Limit edges
                        subgraph_edges.append(edge)

                    if len(visited) >= max_nodes:
                        break

        logger.info(
            f"BFS traversal: {len(subgraph_nodes)} nodes, {len(subgraph_edges)} edges "
            f"(start={len(start_nodes)}, hops≤{hop_limit})"
        )

        return {
            "nodes": subgraph_nodes,
            "edges": subgraph_edges
        }

    def find_paths(
        self,
        start_node: str,
        end_node: str,
        max_hops: int = 4,
        max_paths: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find paths between two nodes

        Args:
            start_node: Start node ID
            end_node: End node ID
            max_hops: Maximum path length
            max_paths: Maximum number of paths to return

        Returns:
            List of paths: [{"nodes": [str], "hops": int, "score": float}]
        """
        if start_node not in self.nodes or end_node not in self.nodes:
            return []

        paths = []
        queue = deque([([start_node], 0)])  # (path, hops)
        visited_paths = set()

        while queue and len(paths) < max_paths:
            path, hops = queue.popleft()
            current = path[-1]

            # Found end node
            if current == end_node:
                path_key = tuple(path)
                if path_key not in visited_paths:
                    visited_paths.add(path_key)
                    score = self._calculate_path_score(path)
                    paths.append({
                        "nodes": path,
                        "hops": hops,
                        "score": round(score, 2)
                    })
                continue

            # Stop if reached max hops
            if hops >= max_hops:
                continue

            # Explore neighbors
            for neighbor_id, edge in self.adj_list.get(current, []):
                if neighbor_id not in path:  # Avoid cycles
                    new_path = path + [neighbor_id]
                    queue.append((new_path, hops + 1))

        # Sort paths by score
        paths.sort(key=lambda p: p["score"], reverse=True)

        logger.info(f"Found {len(paths)} paths from {start_node} to {end_node}")

        return paths[:max_paths]

    def find_k_hop_neighbors(
        self,
        node_id: str,
        k: int = 2
    ) -> List[str]:
        """
        Find all nodes within k hops from node_id

        Args:
            node_id: Starting node
            k: Number of hops

        Returns:
            List of neighbor node IDs
        """
        if node_id not in self.nodes:
            return []

        visited = {node_id}
        current_level = {node_id}

        for hop in range(k):
            next_level = set()
            for node in current_level:
                for neighbor_id, _ in self.adj_list.get(node, []):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_level.add(neighbor_id)

            current_level = next_level

            if not current_level:
                break

        neighbors = list(visited - {node_id})

        logger.info(f"Found {len(neighbors)} neighbors within {k} hops of {node_id}")

        return neighbors

    def extract_subgraph(
        self,
        node_ids: List[str],
        include_edges: bool = True
    ) -> Dict[str, Any]:
        """
        Extract subgraph containing specific nodes

        Args:
            node_ids: Node IDs to include
            include_edges: Whether to include edges between nodes

        Returns:
            Subgraph dict
        """
        node_set = set(node_ids)
        subgraph_nodes = [self.nodes[nid] for nid in node_ids if nid in self.nodes]

        subgraph_edges = []
        if include_edges:
            for edge in self.edges:
                if edge["src"] in node_set and edge["tgt"] in node_set:
                    subgraph_edges.append(edge)

        return {
            "nodes": subgraph_nodes,
            "edges": subgraph_edges
        }

    def _calculate_path_score(self, path: List[str]) -> float:
        """
        Calculate path score based on edge weights

        Returns:
            Score in [0, 1]
        """
        if len(path) < 2:
            return 0.0

        total_weight = 0.0
        edge_count = 0

        for i in range(len(path) - 1):
            src = path[i]
            tgt = path[i + 1]

            # Find edge weight
            for neighbor_id, edge in self.adj_list.get(src, []):
                if neighbor_id == tgt:
                    total_weight += edge.get("weight", 0.5)
                    edge_count += 1
                    break

        if edge_count == 0:
            return 0.0

        avg_weight = total_weight / edge_count

        # Penalize longer paths
        length_penalty = 1.0 / (1.0 + len(path) * 0.1)

        return min(1.0, avg_weight * length_penalty)

    def get_central_nodes(self, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Get most central nodes by degree centrality

        Args:
            top_k: Number of nodes to return

        Returns:
            List of nodes with centrality scores
        """
        centrality = {}

        for node_id in self.nodes:
            degree = len(self.adj_list.get(node_id, []))
            centrality[node_id] = degree

        # Sort by centrality
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

        central_nodes = []
        for node_id, degree in sorted_nodes[:top_k]:
            node = dict(self.nodes[node_id])
            node["centrality"] = degree
            central_nodes.append(node)

        return central_nodes


def create_traversal(graph: Dict[str, Any]) -> GraphTraversal:
    """Factory function to create graph traversal"""
    return GraphTraversal(graph)
