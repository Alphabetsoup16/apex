from __future__ import annotations

import argparse

from apex.cli import llm_cmd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apex",
        description="APEX — MCP verification server and local helpers",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run the MCP server")
    serve.add_argument("--transport", choices=["stdio"], default="stdio")

    _add_local_setup_parser(sub, "init")
    _add_local_setup_parser(sub, "setup")

    return parser


def _add_local_setup_parser(sub, name: str) -> None:
    p = sub.add_parser(
        name,
        help="Local setup (LLM credentials → ~/.apex/config.json)",
    )
    p.add_argument(
        "action",
        nargs="?",
        choices=["show", "clear"],
        metavar="ACTION",
        help="show: config + env summary (no secrets). clear: remove config file. "
        "Default: interactive wizard.",
    )


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.cmd == "serve":
        # Lazy import so `apex init` / `apex setup` do not load MCP/FastMCP.
        from apex.mcp.server import create_mcp_server

        mcp = create_mcp_server()
        mcp.run(transport=args.transport)
    elif args.cmd in ("init", "setup"):
        if args.action == "show":
            llm_cmd.cmd_show()
        elif args.action == "clear":
            llm_cmd.cmd_clear()
        else:
            llm_cmd.cmd_setup()


if __name__ == "__main__":
    main()
