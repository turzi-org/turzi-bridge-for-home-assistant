"""Every screen and button the flows show is worded, in every language."""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent / "custom_components" / "turzi_bridge"
FILES = [ROOT / "strings.json", ROOT / "translations" / "en.json", ROOT / "translations" / "es.json"]
STEPS = {"domain_filter": {"user", "reconfigure", "classes"}, "entity_filter": {"user", "reconfigure"}, "exclusion": {"user", "reconfigure"}}


def test_every_row_type_has_its_button_its_name_and_its_steps():
    for path in FILES:
        strings = json.loads(path.read_text())
        assert set(strings["config_subentries"]) == set(STEPS), path.name
        for kind, steps in STEPS.items():
            block = strings["config_subentries"][kind]
            assert block["entry_type"] and block["initiate_flow"]["user"] and block["initiate_flow"]["reconfigure"], (path.name, kind)
            assert set(block["step"]) == steps, (path.name, kind)


def test_the_options_step_is_worded_at_setup_and_in_configure():
    for path in FILES:
        strings = json.loads(path.read_text())
        for step in (strings["config"]["step"]["settings"], strings["options"]["step"]["init"]):
            assert step["data"]["auto_add_new"] and step["data_description"]["auto_add_new"], path.name
        assert "{filters}" in strings["config"]["step"]["settings"]["description"]
        assert "{held}" in strings["options"]["step"]["init"]["description"]
