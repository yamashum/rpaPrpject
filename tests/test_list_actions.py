from workflow.actions import list_actions, BUILTIN_ACTIONS
from workflow.actions import list_actions, BUILTIN_ACTIONS

def test_list_actions_covers_all():
    categories = list_actions()
    collected = {a for acts in categories.values() for a in acts}
    assert set(BUILTIN_ACTIONS) == collected


def test_advanced_category_present():
    categories = list_actions()
    assert "詳細設定" in categories
    assert "ime.on" in categories["詳細設定"]
