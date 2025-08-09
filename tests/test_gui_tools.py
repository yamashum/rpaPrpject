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
    monkeypatch.setattr(gui_tools, "_screen_dpi", lambda: 120)
    monkeypatch.setattr(gui_tools, "_grab_preview", lambda x, y: (x, y))

    res_screen = gui_tools.capture_coordinates()
    assert res_screen == {"x": 100, "y": 200, "basis": "Screen", "dpi": 120}

    res_elem = gui_tools.capture_coordinates(basis="Element", origin=(90, 190))
    assert (
        res_elem["x"] == 10
        and res_elem["y"] == 10
        and res_elem["basis"] == "Element"
        and res_elem["dpi"] == 120
    )

    res_preview = gui_tools.capture_coordinates(preview=True)
    assert res_preview["preview"] == (100, 200)
    assert res_preview["dpi"] == 120


def test_element_spy_highlight_and_anchor(monkeypatch):
    calls = []

    monkeypatch.setattr(
        gui_tools, "highlight_screen", lambda sel: calls.append(("highlight", sel))
    )
    monkeypatch.setattr(
        gui_tools, "register_anchor", lambda sel: calls.append(("anchor", sel))
    )

    info = gui_tools.element_spy("#login")
    assert info.selector == "#login"
    assert ("highlight", "#login") in calls
    assert ("anchor", "#login") in calls


def test_record_web_normalises_and_wires():
    flow = {"steps": [{"id": "a", "action": "click"}]}
    actions = [{"id": "a", "selector": "button#save"}]
    result = gui_tools.record_web(actions, flow)
    suggestions = result[0]["selectorSuggestions"]
    assert suggestions[0] == "[data-testid=\"save\"]"
    assert result[0]["selector"] == "[data-testid=\"save\"]"
    assert flow["steps"][0]["params"]["selector"] == "[data-testid=\"save\"]"
