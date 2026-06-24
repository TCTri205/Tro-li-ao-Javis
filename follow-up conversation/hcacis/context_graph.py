import os
import logging
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from .models import Entity

logger = logging.getLogger(__name__)

class ContextGraph:
    def __init__(self):
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "password")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Verify connectivity
            self.driver.verify_connectivity()
            self.is_connected = True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j. Falling back to in-memory mode. Error: {e}")
            self.is_connected = False
            self.driver = None
            
    def close(self):
        if self.driver:
            self.driver.close()

    def add_entity(self, entity: Entity):
        """Add or update an entity node in Neo4j."""
        if not self.is_connected:
            return
            
        query = (
            "MERGE (n:Entity {id: $id}) "
            "SET n.type = $type, n.name = $name "
        )
        # Dynamically set attributes
        attrs = {k: str(v) for k, v in entity.attributes.items()}
        
        with self.driver.session() as session:
            session.run(query, id=entity.id, type=entity.type, name=entity.name)
            if attrs:
                # Add attributes
                set_query = "MATCH (n:Entity {id: $id}) SET n += $attrs"
                session.run(set_query, id=entity.id, attrs=attrs)

    def add_relation(self, source_id: str, target_id: str, relation_type: str):
        """Add a directed edge in Neo4j."""
        if not self.is_connected:
            return
            
        query = (
            "MATCH (a:Entity {id: $source_id}) "
            "MATCH (b:Entity {id: $target_id}) "
            f"MERGE (a)-[r:{relation_type}]->(b)"
        )
        with self.driver.session() as session:
            session.run(query, source_id=source_id, target_id=target_id)

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entity details from Neo4j."""
        if not self.is_connected:
            return None
            
        query = "MATCH (n:Entity {id: $id}) RETURN properties(n) as props"
        with self.driver.session() as session:
            result = session.run(query, id=entity_id)
            record = result.single()
            if record:
                return record["props"]
        return None

    def get_related_entities(self, entity_id: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get entities related to the given entity via Graph Traversal."""
        if not self.is_connected:
            return []
            
        rel = f":{relation_type}" if relation_type else ""
        query = (
            f"MATCH (a:Entity {{id: $id}})-[r{rel}]->(b:Entity) "
            "RETURN properties(b) as props"
        )
        
        related = []
        with self.driver.session() as session:
            result = session.run(query, id=entity_id)
            for record in result:
                related.append(record["props"])
        return related

    def resolve_coreference(self, pronoun_or_reference: str, current_active_entity_id: Optional[str]) -> Optional[str]:
        """
        Graph traversal for Coreference Resolution.
        If we have an active entity, we can check its immediate neighbors to resolve references.
        """
        references = ["その", "あの", "この", "彼", "彼女", "その人", "あの人", "その会議", "あの会議", "そこ", "それ", "その件", "nó", "ấy", "đó"]
        if any(ref in pronoun_or_reference.lower() for ref in references):
            if current_active_entity_id:
                # If connected to Neo4j, verify the node exists
                if self.is_connected:
                    if self.get_entity(current_active_entity_id):
                        return current_active_entity_id
                else:
                    return current_active_entity_id
        return None

    def export_subgraph(self, entity_ids: List[str]) -> Dict[str, Any]:
        """Export a subgraph for the LLM to understand active context."""
        if not self.is_connected:
            return {"nodes": [], "links": []}
            
        query = (
            "MATCH (n:Entity) WHERE n.id IN $ids "
            "OPTIONAL MATCH (n)-[r]->(m:Entity) WHERE m.id IN $ids "
            "RETURN properties(n) as node, type(r) as rel, properties(m) as target"
        )
        
        nodes = {}
        links = []
        
        with self.driver.session() as session:
            result = session.run(query, ids=entity_ids)
            for record in result:
                node = record["node"]
                if node["id"] not in nodes:
                    nodes[node["id"]] = node
                
                if record["rel"] and record["target"]:
                    links.append({
                        "source": node["id"],
                        "target": record["target"]["id"],
                        "type": record["rel"]
                    })
                    
        return {"nodes": list(nodes.values()), "links": links}
