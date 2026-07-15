from __future__ import annotations


def build_event_key(*, machine_id: str, camera_code: str, business_date: str, capture_id: str) -> str:
    return "|".join([machine_id, camera_code, business_date, capture_id])
