"""LLM model config and test services."""

from __future__ import annotations

from shared import (
    _models_lock,
    _sanitize_model_for_client,
    API_TYPE_CCB,
    API_TYPE_OPENAI,
    call_llm,
    call_llm_with_retry,
    extract_assistant_content,
    get_model_by_name,
    iter_llm_stream,
    load_base_presets,
    load_custom_models,
    load_llm_config,
    load_preset_overrides,
    normalize_llm_url,
    save_custom_models,
    save_preset_overrides,
)


def list_models() -> dict:
    models = load_llm_config()
    result = [_sanitize_model_for_client(m) for m in models]
    return {"status": "ok", "models": result}


def parse_model_payload(data, existing=None, require_api_key=True):
    """Parse and validate model fields from request JSON."""
    name = (data.get("name") or (existing or {}).get("name") or "").strip()
    raw_url = (data.get("url") or (existing or {}).get("url") or "").strip()
    model = (data.get("model") or (existing or {}).get("model") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    if not api_key and existing:
        api_key = (existing.get("api_key") or "").strip()
    api_type = (data.get("api_type") or (existing or {}).get("api_type") or API_TYPE_OPENAI).strip().lower()
    if api_type not in (API_TYPE_OPENAI, API_TYPE_CCB):
        return None, f"api_type 无效，应为 {API_TYPE_OPENAI} 或 {API_TYPE_CCB}"
    url = normalize_llm_url(raw_url, api_type)
    if not all([name, url, model]):
        return None, "name/url/model 均为必填"
    if require_api_key and not api_key:
        return None, "api_key 为必填"
    tx_code = (data.get("tx_code") or (existing or {}).get("tx_code") or "").strip()
    sec_node_no = (data.get("sec_node_no") or (existing or {}).get("sec_node_no") or "").strip()
    if api_type == API_TYPE_CCB:
        if not tx_code or not sec_node_no:
            return None, "建行接口需填写 Tx-Code 与 Sec-Node-No"
    parsed = {
        "name": name,
        "url": url,
        "model": model,
        "api_key": api_key,
        "api_type": api_type,
        "max_tokens": data.get("max_tokens", (existing or {}).get("max_tokens", 4096)),
        "temperature": data.get("temperature", (existing or {}).get("temperature", 0.7)),
        "description": data.get("description", (existing or {}).get("description", "")),
    }
    if api_type == API_TYPE_CCB:
        parsed["tx_code"] = tx_code
        parsed["sec_node_no"] = sec_node_no
        fst = (data.get("fst_attr_rmrk") or (existing or {}).get("fst_attr_rmrk") or "").strip()
        if fst:
            parsed["fst_attr_rmrk"] = fst
    return parsed, None


def add_model(data: dict) -> dict:
    parsed, err = parse_model_payload(data, require_api_key=True)
    if err:
        return {"status": "error", "error": err}
    name = parsed["name"]

    with _models_lock:
        custom = load_custom_models()
        existing_names = [m["name"] for m in load_llm_config()]
        if name in existing_names:
            return {"status": "error", "error": f"模型名称 '{name}' 已存在"}
        custom.append(parsed)
        save_custom_models(custom)

    return {"status": "ok", "message": f"模型 '{name}' 已添加"}


def get_model(model_name: str) -> dict:
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return {"status": "error", "error": f"模型 '{model_name}' 不存在"}
    d = _sanitize_model_for_client(model_cfg)
    d["is_preset"] = model_cfg.get("is_preset", False)
    return {"status": "ok", "model": d}


def update_model(model_name: str, data: dict) -> dict:
    existing = get_model_by_name(model_name)
    if not existing:
        return {"status": "error", "error": f"模型 '{model_name}' 不存在"}

    parsed, err = parse_model_payload(data, existing=existing, require_api_key=False)
    if err:
        return {"status": "error", "error": err}

    new_name = parsed["name"]
    if new_name != model_name:
        return {"status": "error", "error": "暂不支持修改模型名称，请删除后重新添加"}

    save_fields = {k: v for k, v in parsed.items() if k != "name"}

    with _models_lock:
        if existing.get("is_preset"):
            overrides = load_preset_overrides()
            overrides[model_name] = save_fields
            save_preset_overrides(overrides)
        else:
            custom = load_custom_models()
            updated = False
            for i, m in enumerate(custom):
                if m["name"] == model_name:
                    custom[i] = parsed
                    updated = True
                    break
            if not updated:
                return {"status": "error", "error": f"自定义模型 '{model_name}' 不存在"}
            save_custom_models(custom)

    return {"status": "ok", "message": f"模型 '{model_name}' 已更新"}


def delete_model(model_name: str) -> dict:
    with _models_lock:
        custom = load_custom_models()
        before = len(custom)
        custom = [m for m in custom if m["name"] != model_name]
        if len(custom) == before:
            return {"status": "error", "error": f"自定义模型 '{model_name}' 不存在或为预设模型不可删除"}
        save_custom_models(custom)
    return {"status": "ok", "message": f"模型 '{model_name}' 已删除"}


def test_model(model_name: str, lang: str = "zh-CN") -> dict:
    model_cfg = get_model_by_name(model_name)
    is_en = bool(lang and lang.startswith("en"))
    if not model_cfg:
        return {
            "status": "error",
            "error": f"Model '{model_name}' not found" if is_en else f"模型 '{model_name}' 不存在",
        }
    try:
        from llm_client import LlmApiError
        test_cfg = dict(model_cfg)
        test_cfg["timeout"] = min(int(test_cfg.get("timeout", 300)), 20)
        result = call_llm(
            test_cfg,
            [{"role": "user", "content": "Hi"}],
            stream=False,
            max_tokens=10,
        )
        content = extract_assistant_content(result) if isinstance(result, dict) else ""
        if is_en:
            return {"status": "ok", "message": f"Connection successful. Response: {content[:50]}"}
        return {"status": "ok", "message": f"连接成功，模型回复: {content[:50]}"}
    except Exception as e:
        from llm_client import LlmApiError
        if isinstance(e, LlmApiError):
            return {"status": "error", "error": str(e)}
        if is_en:
            return {"status": "error", "error": f"Connection failed: {str(e)}"}
        return {"status": "error", "error": f"连接失败: {str(e)}"}


def stream_test_model(model_name: str, prompt: str, lang: str = "zh-CN"):
    from flask import Response, stream_with_context
    import json

    is_en = bool(lang and lang.startswith("en"))
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        msg = f"Model '{model_name}' not found" if is_en else f"模型 '{model_name}' 不存在"
        err = json.dumps({"error": msg}, ensure_ascii=False)
        return Response(err, mimetype="text/event-stream")

    messages = [{"role": "user", "content": prompt}]

    def generate():
        try:
            from llm_client import LlmApiError
            test_cfg = dict(model_cfg)
            test_cfg["timeout"] = min(int(test_cfg.get("timeout", 300)), 120)
            resp = call_llm(test_cfg, messages, stream=True, max_tokens=256)
            for delta in iter_llm_stream(test_cfg, resp):
                payload = json.dumps({"delta": delta}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            if isinstance(e, LlmApiError):
                err = json.dumps({"error": str(e)}, ensure_ascii=False)
            else:
                msg = f"Stream connection failed: {str(e)}" if is_en else f"流式连接失败: {str(e)}"
                err = json.dumps({"error": msg}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
