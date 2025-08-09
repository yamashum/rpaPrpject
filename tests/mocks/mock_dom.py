class MockDOM:
    """Simple mock DOM object to track text content."""
    def __init__(self):
        self.text = "initial"

    def change(self, new_text: str) -> str:
        """Simulate a DOM update by changing the text content."""
        self.text = new_text
        return self.text

    def query(self) -> str:
        """Return the current text content."""
        return self.text
