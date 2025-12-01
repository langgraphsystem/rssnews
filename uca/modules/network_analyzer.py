import networkx as nx
import community.community_louvain as community_louvain
import re
from collections import Counter
from typing import List, Dict, Any, Tuple
import logging
from textblob import TextBlob

logger = logging.getLogger(__name__)

class NetworkAnalyzer:
    """
    Analyzes text to build a network graph of co-occurring words,
    identifying topics (communities) and influential terms.
    """
    
    def __init__(self, window_size: int = 4, min_edge_weight: int = 2):
        self.window_size = window_size
        self.min_edge_weight = min_edge_weight
        self.stopwords = set([
            'the', 'and', 'to', 'of', 'a', 'in', 'is', 'that', 'for', 'it', 'on', 'with', 'as', 
            'are', 'was', 'this', 'at', 'be', 'by', 'an', 'have', 'from', 'or', 'you', 'not', 
            'but', 'what', 'all', 'were', 'when', 'we', 'there', 'can', 'your', 'which', 'their', 
            'if', 'do', 'will', 'so', 'how', 'about', 'out', 'up', 'one', 'has', 'more', 'they',
            'alt', 'src', 'href', 'class', 'style', 'width', 'height', 'img', 'post', 'appeared', 'first'
        ])

    def preprocess(self, text: str) -> List[str]:
        """Clean and tokenize text."""
        # Remove HTML
        text = re.sub(r'<[^>]+>', '', text)
        # Remove URLs
        text = re.sub(r'http\S+', '', text)
        # Lowercase and remove non-alphanumeric
        text = re.sub(r'[^\w\s]', '', text.lower())
        
        tokens = text.split()
        return [t for t in tokens if t not in self.stopwords and len(t) > 2]

    def build_graph(self, text: str) -> nx.Graph:
        """Build a co-occurrence graph from text."""
        tokens = self.preprocess(text)
        G = nx.Graph()
        
        # Add nodes
        for token in tokens:
            G.add_node(token)
            
        # Add edges (sliding window)
        for i in range(len(tokens) - self.window_size + 1):
            window = tokens[i : i + self.window_size]
            for j in range(len(window)):
                for k in range(j + 1, len(window)):
                    u, v = window[j], window[k]
                    if u != v:
                        if G.has_edge(u, v):
                            G[u][v]['weight'] += 1
                        else:
                            G.add_edge(u, v, weight=1)
                            
        # Filter weak edges
        edges_to_remove = [(u, v) for u, v, d in G.edges(data=True) if d['weight'] < self.min_edge_weight]
        G.remove_edges_from(edges_to_remove)
        
        # Remove isolated nodes
        G.remove_nodes_from(list(nx.isolates(G)))
        
        return G

    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Perform full network analysis: graph build, community detection, centrality.
        Returns data suitable for visualization.
        """
        G = self.build_graph(text)
        
        if len(G.nodes) == 0:
            return {"nodes": [], "edges": [], "communities": {}}

        # Community Detection (Louvain)
        try:
            partition = community_louvain.best_partition(G)
        except ImportError:
            logger.warning("python-louvain not installed, skipping community detection")
            partition = {node: 0 for node in G.nodes()}
        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            partition = {node: 0 for node in G.nodes()}

        # Centrality (Betweenness is key for InfraNodus)
        # Degree centrality shows frequency, Betweenness shows influence/bridges
        degree = nx.degree_centrality(G)
        betweenness = nx.betweenness_centrality(G)
        
        # Sentiment Analysis (Node-level)
        # We estimate sentiment of a word by averaging sentiment of sentences it appears in
        blob = TextBlob(text)
        word_sentiments = {}
        for sentence in blob.sentences:
            sent_score = sentence.sentiment.polarity
            for word in sentence.words:
                w_lower = word.lower()
                if w_lower in G.nodes():
                    if w_lower not in word_sentiments:
                        word_sentiments[w_lower] = []
                    word_sentiments[w_lower].append(sent_score)
        
        # Average sentiment per node
        node_sentiment = {}
        for node in G.nodes():
            scores = word_sentiments.get(node, [0.0])
            avg_score = sum(scores) / len(scores)
            node_sentiment[node] = avg_score

        # Identify Structural Gaps
        # Find top nodes in different communities that are NOT connected
        gaps = []
        top_nodes = sorted(G.nodes(), key=lambda n: betweenness[n], reverse=True)[:20]
        for i in range(len(top_nodes)):
            for j in range(i + 1, len(top_nodes)):
                u, v = top_nodes[i], top_nodes[j]
                # If in different communities and no edge
                if partition[u] != partition[v] and not G.has_edge(u, v):
                    gaps.append({
                        "node_a": u,
                        "node_b": v,
                        "topic_a": partition[u],
                        "topic_b": partition[v],
                        "score": betweenness[u] + betweenness[v] # Priority score
                    })
        
        # Sort gaps by importance
        gaps = sorted(gaps, key=lambda x: x['score'], reverse=True)[:5]
        
        # Prepare data for PyVis / JSON
        nodes = []
        for node in G.nodes():
            sent = node_sentiment.get(node, 0.0)
            # Color based on sentiment? Or Community?
            # InfraNodus uses Community for color, but maybe we can use shape or border for sentiment?
            # For now, let's keep Community color but add sentiment to title
            
            nodes.append({
                "id": node,
                "label": node,
                "value": degree[node] * 10, # Size based on degree (frequency)
                "group": partition[node], # Color by community
                "title": f"Topic {partition[node]} | BC: {betweenness[node]:.4f} | Sent: {sent:.2f}",
                "sentiment": sent
            })
            
        edges = []
        for u, v, d in G.edges(data=True):
            edges.append({
                "from": u,
                "to": v,
                "value": d['weight'] # Thickness based on weight
            })
            
        return {
            "nodes": nodes,
            "edges": edges,
            "communities": partition,
            "centrality": betweenness,
            "structural_gaps": gaps,
            "graph_object": G
        }
