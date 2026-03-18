from __future__ import annotations

import argparse

from apex.server import create_mcp_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="apex", description="APEX MCP server")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run the MCP server")
    serve.add_argument("--transport", choices=["stdio"], default="stdio")

    args = parser.parse_args()

    if args.cmd == "serve":
        mcp = create_mcp_server()
        # FastMCP stdio is the default; we pass it explicitly for clarity.
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

