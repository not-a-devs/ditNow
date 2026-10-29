import json
import shutil
from pathlib import Path

import pytest

from app.config import ROOT_DIR
from app.data_loader import DataError, load_data
from tests.conftest import FIXTURES


def test_real_data_loads() -> None:
    """실제 data/ 폴더가 스키마·참조 검증을 통과한다."""
    data = load_data(ROOT_DIR / "data")
    assert len(data.facilities) > 50
    assert "jeongbo" in data.buildings


def _broken_copy(tmp_path: Path, mutate) -> Path:
    """픽스처를 복사한 뒤 facilities.json만 변형한다."""
    shutil.copy(FIXTURES / "buildings.json", tmp_path / "buildings.json")
    items = json.loads((FIXTURES / "facilities.json").read_text(encoding="utf-8"))
    mutate(items)
    (tmp_path / "facilities.json").write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_duplicate_id(tmp_path: Path) -> None:
    """id가 중복되면 에러."""
    d = _broken_copy(tmp_path, lambda items: items.append(dict(items[0])))
    with pytest.raises(DataError, match="중복"):
        load_data(d)


def test_broken_building_ref(tmp_path: Path) -> None:
    """없는 building_id를 가리키면 에러."""
    d = _broken_copy(tmp_path, lambda items: items[0].update(building_id="nowhere"))
    with pytest.raises(DataError, match="nowhere"):
        load_data(d)


def test_schema_error_names_file_and_id(tmp_path: Path) -> None:
    """필수 필드가 빠지면 파일명과 항목 id가 에러에 포함된다."""
    d = _broken_copy(tmp_path, lambda items: items[0].pop("text"))
    with pytest.raises(DataError, match=r"facilities\.json \[") as e:
        load_data(d)
    assert "text" in str(e.value)
