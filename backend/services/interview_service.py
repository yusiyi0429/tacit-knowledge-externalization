"""Interview probe business services."""

from __future__ import annotations

from shared import call_llm_with_retry, extract_assistant_content, get_model_by_name, load_llm_config


def _llm_call_for_interview(system_prompt: str, user_prompt: str, model_name: str) -> str:
    """访谈专用的 LLM 调用封装"""
    cfg = get_model_by_name(model_name)
    if not cfg:
        raise ValueError(f"模型 '{model_name}' 不可用")
    result = call_llm_with_retry(
        cfg,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2048,
        temperature=0.7,
    )
    return extract_assistant_content(result) if isinstance(result, dict) else str(result)


def probe(method: str, knowledge_item: dict, model_name: str) -> dict:
    from interview_session import build_interview_prompt, INTERVIEW_METHODS, parse_interview_result

    if not knowledge_item:
        return {"status": "error", "error": "请提供知识条目"}
    if method not in ("case_reverse", "contrast_probe", "limit_hypothesis"):
        return {"status": "error", "error": f"未知访谈方法: {method}"}

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return {"status": "error", "error": f"模型不存在: {model_name}"}

    system_prompt, user_prompt = build_interview_prompt(method, knowledge_item)
    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], stream=False, temperature=0.3, max_tokens=1024)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
        probes = parse_interview_result(raw)
        return {
            "status": "ok",
            "method": method,
            "method_name": INTERVIEW_METHODS.get(method, {}).get("name", method),
            "probes": probes,
        }
    except Exception as e:
        return {"status": "error", "error": f"访谈追问生成失败: {str(e)}"}
