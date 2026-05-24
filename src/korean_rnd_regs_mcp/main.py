"""korean-rnd-regs-mcp main entry — stdio MCP server."""
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP

from . import __version__

load_dotenv()

logger = logging.getLogger("rnd-regs-mcp")
_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger.setLevel(_level)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(_handler)

mcp = FastMCP("korean-rnd-regs-mcp")


@mcp.tool()
async def health() -> dict:
    """서비스 상태 확인 — status, service name, version, API 키 설정 여부."""
    return {
        "status": "ok",
        "service": "korean-rnd-regs-mcp",
        "version": __version__,
        "api_key_configured": bool(os.environ.get("LAW_API_KEY")),
    }


@mcp.tool()
async def list_rule_sets() -> dict:
    """등록된 규정 문서(rule set) 목록 — Phase 3 Step 19/20에서 실제 manifest 입력 전까지 stub."""
    return {
        "rule_sets": [],
        "note": "manifest stub — Phase 3에서 혁신법·시행령·핵심 행정규칙 입력 예정",
    }


async def _run() -> None:
    logger.info("korean-rnd-regs-mcp stdio server starting")
    await mcp.run_stdio_async()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
