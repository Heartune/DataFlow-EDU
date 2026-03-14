# -*- coding: utf-8 -*-
"""CLI: 接收 JSON 配置，校验并保存。供 WebUI 后端调用。"""

import importlib.util
import json
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_config_dir = os.path.dirname(_script_dir)
_project_root = os.path.dirname(os.path.dirname(_config_dir))

# Load loader and validator without pulling in dataflow_edu.__init__ (operators)
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    if name == "dataflow_edu.config.schema":
        pass
    elif name == "dataflow_edu.config.loader":
        # loader needs schema
        schema_path = os.path.join(_config_dir, "schema.py")
        if "dataflow_edu.config.schema" not in sys.modules:
            _load_module("dataflow_edu.config.schema", schema_path)
    spec.loader.exec_module(mod)
    return mod

schema_path = os.path.join(_config_dir, "schema.py")
loader_path = os.path.join(_config_dir, "loader.py")
validator_path = os.path.join(_config_dir, "validator.py")

_load_module("dataflow_edu.config.schema", schema_path)
loader = _load_module("dataflow_edu.config.loader", loader_path)
validator_mod = _load_module("dataflow_edu.config.validator", validator_path)

_dict_to_config = loader._dict_to_config
save_config = loader.save_config
get_config_path = loader.get_config_path
validate_config = validator_mod.validate_config


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "errors": [f"JSON 解析失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    try:
        config = _dict_to_config(data, project_root=_project_root)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [f"配置转换失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    is_valid, errors = validate_config(config, project_root=_project_root, check_paths=False)
    if not is_valid:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        sys.exit(1)

    try:
        save_config(config, path=get_config_path(_project_root), project_root=_project_root)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [f"保存失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
