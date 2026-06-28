[tool:pytest.ini_options]
asyncio_mode = auto
testpaths = ["tests"]
markers = [
    "e2e: Playwright browser tests (run separately)",
]
