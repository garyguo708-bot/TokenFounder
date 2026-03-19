from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanvasItem:
    content: list[str]
    is_inferred: bool = False


@dataclass
class BusinessCanvas:
    project_name: str
    tagline: str
    customer_segments: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    value_propositions: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    channels: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    customer_relationships: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    revenue_streams: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    key_resources: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    key_activities: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    key_partnerships: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    cost_structure: CanvasItem = field(default_factory=lambda: CanvasItem([]))
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "tagline": self.tagline,
            "canvas": {
                "customer_segments": {"content": self.customer_segments.content, "is_inferred": self.customer_segments.is_inferred},
                "value_propositions": {"content": self.value_propositions.content, "is_inferred": self.value_propositions.is_inferred},
                "channels": {"content": self.channels.content, "is_inferred": self.channels.is_inferred},
                "customer_relationships": {"content": self.customer_relationships.content, "is_inferred": self.customer_relationships.is_inferred},
                "revenue_streams": {"content": self.revenue_streams.content, "is_inferred": self.revenue_streams.is_inferred},
                "key_resources": {"content": self.key_resources.content, "is_inferred": self.key_resources.is_inferred},
                "key_activities": {"content": self.key_activities.content, "is_inferred": self.key_activities.is_inferred},
                "key_partnerships": {"content": self.key_partnerships.content, "is_inferred": self.key_partnerships.is_inferred},
                "cost_structure": {"content": self.cost_structure.content, "is_inferred": self.cost_structure.is_inferred},
            },
            "next_steps": self.next_steps,
        }
