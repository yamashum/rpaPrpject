import types
import queue
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

    info = gui_tools.element_spy("#login", text="Login")
    assert info.selector == "#login"
    assert info.automation_id and info.name and info.control_type and info.class_name
    assert isinstance(info.hierarchy, list)
    assert ("highlight", "#login") in calls
    assert ("anchor", "#login") in calls

    rows = gui_tools.format_spy_result(info)
    keys = [k for k, _ in rows]
    assert "AutomationId" in keys and "Hierarchy" in keys


def test_record_web_normalises_and_wires():
    flow = {"steps": [{"id": "a", "action": "click"}]}
    actions = [{"id": "a", "selector": "button#save"}]
    result = gui_tools.record_web(actions, flow)
    suggestions = result[0]["selectorSuggestions"]
    assert suggestions[0] == "[data-testid=\"save\"]"
    assert result[0]["selector"] == "[data-testid=\"save\"]"
    assert flow["steps"][0]["params"]["selector"] == "[data-testid=\"save\"]"


def test_record_web_insert_callback_and_queue():
    q: queue.Queue = queue.Queue()
    calls: list[dict] = []
    actions = [{"selector": "button#ok"}]
    gui_tools.record_web(
        actions,
        insert=True,
        callback=lambda a: calls.append(a),
        queue=q,
    )
    assert calls[0]["selector"].startswith("[data-testid=")
    queued = q.get_nowait()
    assert queued["selector"] == calls[0]["selector"]


def test_spy_on_click(monkeypatch):
    monkeypatch.setattr(
        gui_tools, "capture_coordinates", lambda wait=True: {"x": 1, "y": 2, "basis": "Screen", "dpi": 96}
    )

    captured: list[tuple[str, int, int]] = []

    def fake_spy(selector: str, text: str | None = None, *, x: int | None = None, y: int | None = None):
        captured.append((selector, x or 0, y or 0))
        return gui_tools.ElementInfo(selector=selector, x=x, y=y)

    monkeypatch.setattr(gui_tools, "element_spy", fake_spy)

    info = gui_tools.spy_on_click()
    assert captured[0] == ("@1,2", 1, 2)
    assert info.x == 1 and info.y == 2

def test_countdown_capture_coordinates(monkeypatch):
    called = {}

    def fake_capture():
        called["done"] = True
        return {"x": 5, "y": 6}

    sleeps: list[int] = []
    def fake_sleep(sec: int) -> None:
        sleeps.append(sec)

    monkeypatch.setattr(gui_tools, "capture_coordinates", fake_capture)
    monkeypatch.setattr(gui_tools.time, "sleep", fake_sleep)

    res = gui_tools.countdown_capture_coordinates(seconds=3)
    assert called["done"]
    assert res["x"] == 5 and res["y"] == 6
    assert sleeps == [1, 1, 1]
