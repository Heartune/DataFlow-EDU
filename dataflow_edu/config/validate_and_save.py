# -*- coding: utf-8 -*-
"""CLI: 接收 JSON 配置，校验并保存。供 WebUI 后端调用。"""

import json
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ["DATAFLOW_EDU_CONFIG_ONLY"] = "1"

from dataflow_edu.config.loader import _dict_to_config, save_config, get_config_path
from dataflow_edu.config.validator import validate_config


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
