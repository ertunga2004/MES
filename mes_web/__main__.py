from __future__ import annotations


def main() -> None:
    try:
        import uvicorn
        from .app import app, config
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency: {exc.name}. Install mes_web/requirements.txt first.") from exc

    uvicorn.run(app, host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
