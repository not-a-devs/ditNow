import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.factory import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def schema_text() -> str:
    app = create_app(Settings(environment="test"))
    return json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export or verify the real public FastAPI contract"
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    expected = schema_text()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            print("OpenAPI snapshot is stale. Run python -m app.export_openapi.")
            return 1
        print("OpenAPI snapshot matches the application.")
        return 0
    args.output.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
