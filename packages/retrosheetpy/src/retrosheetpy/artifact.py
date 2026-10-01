"""Metadata describing a downloaded source file."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from retrosheetpy.catalog import Product


@dataclass(frozen=True)
class Artifact:
    source_url: str
    product: Product
    season: int | None
    group: str | None
    local_path: Path
    sha256: str
    size: int
    retrieved_at: datetime

    def to_json(self) -> str:
        return json.dumps(
            {
                "source_url": self.source_url,
                "product": self.product.value,
                "season": self.season,
                "group": self.group,
                "local_path": str(self.local_path),
                "sha256": self.sha256,
                "size": self.size,
                "retrieved_at": self.retrieved_at.isoformat(),
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> "Artifact":
        d = json.loads(text)
        return cls(
            source_url=d["source_url"],
            product=Product(d["product"]),
            season=d["season"],
            group=d["group"],
            local_path=Path(d["local_path"]),
            sha256=d["sha256"],
            size=d["size"],
            retrieved_at=datetime.fromisoformat(d["retrieved_at"]),
        )
