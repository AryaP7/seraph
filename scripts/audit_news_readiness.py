"""C13/C12 audit: inspect an isolated news-store copy and synthetic event semantics."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.dashboard.news_view import build_news_payload
from seraph.news.acquisition import NewsStore
from seraph.news.extraction import extract
from seraph.news.model import Asset, Entity, Place, Story
from seraph.news.registry import MasterData, load_master_data
from seraph.news.estimation import direction_of, evidence_confidence_of
from seraph.product_types import Timing
from seraph.shared_types import IST, ist_timestamp


def main():
    target = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              ROOT / "docs/evidence/INDEPENDENT-NEWS-2026-10-16.json")
    if target.exists():
        raise SystemExit("Refusing to overwrite audit evidence")
    now = ist_timestamp(datetime.now(IST))
    with tempfile.TemporaryDirectory(prefix="seraph-news-audit-") as tmp:
        copied = Path(tmp) / "news.sqlite"
        source = ROOT / "prototype_runs/news.sqlite"
        with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(copied)) as dest:
                src.backup(dest)
        master, _ = load_master_data()
        store = NewsStore(copied)
        payload = build_news_payload(store, master, decision_ts=now)
        actual = {
            "source_coverage": payload["source_coverage"],
            "connected_surfaces_if_builder_were_called": payload["connected_surfaces"],
            "preview_surfaces": payload["preview_surfaces"],
            "registry": payload["registry"],
            "visible_story_count": len(store.stories(visible_at=now)),
            "latest_first_seen": max((s.first_seen_at for s in store.stories()), default=None),
            "latest_published": max((s.timing.published_at or "" for s in store.stories()), default=None),
            "event_types_in_signal_rail": [i["event_type"] for i in payload["surfaces"]["signals"].get("items", [])],
        }

    stamp = "2026-10-16T11:00:00+05:30"
    def story(index, title, source="one_wire"):
        return Story(f"audit_{index}", source, f"obs_{index}", title,
                     "https://audit.invalid/story", Timing(first_seen_at=stamp, published_at=stamp),
                     syndication_group="synthetic_one_event")

    registry = MasterData(
        entities=(Entity("steel", "Tata Steel", "issuer", sector="steel"),),
        places=(Place("india", "India", "country"),
                Place("odisha", "Odisha", "state", parent_id="india")),
        assets=(Asset("plant", "Kalinganagar", "plant", "odisha", operator_entity_id="steel"),))
    event = extract([story(1, "Tata Steel halts production at Kalinganagar in Odisha")], registry).event
    copies = extract([story(i, "Tata Steel halts production") for i in range(10)], registry).event
    cut = extract([story(1, "RBI cuts repo rate by 0.25 percent")], registry).event
    hike = extract([story(2, "RBI raises repo rate by 0.25 percent")], registry).event
    findings = {
        "created_at": now,
        "actual_store_projection": actual,
        "synthetic_facility_event": {
            "affected": event.affected, "actors": event.actors,
            "direct_asset_resolution_exists": registry.resolve_asset("Kalinganagar").describe(),
            "extractor_resolved_facility": "plant" in event.affected,
            "extractor_resolved_place": "odisha" in event.affected,
        },
        "synthetic_same_source_copies": {
            "unique_source_count": 1, "stories": len(copies.stories),
            "reported_confirmations": copies.confirmations,
            "confidence_with_medium_path": evidence_confidence_of(copies, "medium"),
        },
        "synthetic_opposite_policy_moves": {
            "cut_type": cut.event_type, "cut_direction": direction_of(cut),
            "hike_type": hike.event_type, "hike_direction": direction_of(hike),
            "note": "event-level fixed direction; no target-specific economic interpretation",
        },
        "canonical_frontend_calls_builder": "build_news_payload" in (ROOT / "seraph/dashboard/prototype_app.py").read_text(),
    }
    target.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
