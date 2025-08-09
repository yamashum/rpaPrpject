class MockNetwork:
    """Mock network module to simulate failures."""
    def __init__(self):
        self.fail = False

    def get(self, url: str):
        """Pretend to fetch data from a URL.

        Raises
        ------
        ConnectionError
            If ``fail`` is True.
        """
        if self.fail:
            raise ConnectionError("Simulated network failure")
        return {"url": url, "status": 200}
