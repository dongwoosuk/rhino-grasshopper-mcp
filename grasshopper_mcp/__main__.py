"""
Entry point for running as: python -m grasshopper_mcp.bridge
"""

from .bridge import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
