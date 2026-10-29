import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas import Building, CampusData, Facility

M = TypeVar("M", bound=BaseModel)


class DataError(Exception):
    """데이터 JSON이 스키마나 참조 규칙에 맞지 않을 때 발생한다."""


def _load_list(path: Path, model: type[M], id_key: str) -> dict[str, M]:
    """JSON 배열 파일을 읽어 id → 모델 dict로 만든다."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DataError(f"{path.name}: 파일을 읽을 수 없습니다 ({e})") from e
    if not isinstance(raw, list):
        raise DataError(f"{path.name}: 최상위는 배열이어야 합니다")

    docs: dict[str, M] = {}
    for i, item in enumerate(raw):
        item_id = item.get(id_key, f"#{i}") if isinstance(item, dict) else f"#{i}"
        try:
            doc = model.model_validate(item)
        except ValidationError as e:
            raise DataError(f"{path.name} [{item_id}]: {e}") from e
        if item_id in docs:
            raise DataError(f"{path.name} [{item_id}]: id가 중복됩니다")
        docs[item_id] = doc
    return docs


def load_data(data_dir: Path) -> CampusData:
    """data 폴더의 JSON을 읽고 검증한다. 문제가 있으면 DataError."""
    buildings = _load_list(data_dir / "buildings.json", Building, "building_id")
    facilities = _load_list(data_dir / "facilities.json", Facility, "id")
    for fac in facilities.values():
        if fac.building_id is not None and fac.building_id not in buildings:
            raise DataError(
                f"facilities.json [{fac.id}]: 없는 building_id '{fac.building_id}'를 가리킵니다"
            )
    return CampusData(facilities=facilities, buildings=buildings)
