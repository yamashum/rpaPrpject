import types
from workflow import gui_tools


def test_capture_coordinates_basis_preview(monkeypatch):
    class DummyPos:
        def x(self):
            return 100

        def y(self):
            return 200

    dummy_cursor = types.SimpleNamespace(pos=lambda: DummyPos())
    monkeypatch.setattr(gui_tools, "QCursor", dummy_cursor)

    res_screen = gui_tools.capture_coordinates()
    assert res_screen == {"x": 100, "y": 200, "basis": "Screen"}

    res_elem = gui_tools.capture_coordinates(basis="Element", origin=(90, 190))
    assert res_elem["x"] == 10 and res_elem["y"] == 10 and res_elem["basis"] == "Element"

    res_preview = gui_tools.capture_coordinates(preview=True)
    assert res_preview["preview"] == (100, 200)


def test_record_web_suggests_stable_selectors():
    actions = [{"selector": "button#save"}]
    result = gui_tools.record_web(actions)
    suggestions = result[0]["selectorSuggestions"]
    assert suggestions[0] == "[data-testid=\"save\"]"
    assert "#save" in suggestions
