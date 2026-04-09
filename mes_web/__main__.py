from __future__ import annotations

import asyncio
import sys


def _configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy_cls is None:
        return
    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, selector_policy_cls):
        asyncio.set_event_loop_policy(selector_policy_cls())


def main() -> None:
    try:
        import uvicorn
        from .app import app, config
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency: {exc.name}. Install mes_web/requirements.txt first.") from exc

    _configure_event_loop_policy()
    uvicorn.run(app, host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
