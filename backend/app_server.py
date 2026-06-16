#!/usr/bin/env python3
"""Flask backend server for the Tacit Knowledge Extraction web application."""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path

import yaml
from flask import Flask, request, jsonify, send_file, send_from_directory, Response, stream_with_context
from llm_client import (
    API_TYPE_CCB,
    API_TYPE_OPENAI,
    LlmApiError,
    call_llm,
    call_llm_with_retry,
    extract_assistant_content,
    iter_llm_stream,
    normalize_llm_url,
)
import openpyxl

from pipeline_artifacts import (
    basename_only,
    downstream_output_keys,
    keys_to_clear_from_step,
    infer_file_step,
    is_download_allowed,
    is_step1_filename,
    is_step2_preextract_filename,
    is_step3_revision_filename,
    is_step3_final_filename,
    locate_workspace_file,
    resolve_cache_file_path,
    resolve_client_excel_path,
    safe_workspace_path,
    validate_step_data_patch,
    resolve_knowledge_workbook_path,
    resolve_knowledge_ir_path,
    is_skill_draft_filename,
    workspace_path_for,
    PROTECTED_WORKSPACE_FILES,
)
from release_info import STEP2_EXCEL_BUILD, get_release_info
from knowledge_fusion import (
    merge_extraction_results,
    fuse_sources,
    detect_duplicates,
    detect_conflicts,
    interview_answers_to_records,
    aggregate_signals,
)
from interview_session import (
    execute_interview_session,
    collect_interview_answers,
    build_interview_prompt,
    INTERVIEW_METHODS,
)

# 旧部署曾误用私有函数名，保留别名避免 NameError
_is_step2_preextract_filename = is_step2_preextract_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

# Add scripts directory to Python path for skill imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SAMPLES_DIR = PROJECT_DIR / "data" / "samples"
CONFIG_DIR = PROJECT_DIR / "config"
FRONTEND_DIR = PROJECT_DIR / "frontend"
SCHEMA_PATH = CONFIG_DIR / "scenario-schema.yaml"
LLM_CONFIG_PATH = CONFIG_DIR / "llm-config.yaml"
LLM_CONFIG_LOCAL_PATH = CONFIG_DIR / "llm-config.local.yaml"

# Optional API token auth (set APP_AUTH_TOKEN in production)
APP_AUTH_TOKEN = os.environ.get("APP_AUTH_TOKEN", "").strip()

# Workspace: where uploaded/generated files are stored.
# Precedence: --workspace CLI > WORKSPACE_DIR env > project-local data/workspace.
PROJECT_WORKSPACE = PROJECT_DIR / "data" / "workspace"
OLD_DEFAULT_WORKSPACE = Path(tempfile.gettempdir()) / "tacit_knowledge_app"


def _resolve_workspace(cli_workspace: str | None = None) -> Path:
    if cli_workspace:
        return Path(cli_workspace).expanduser().resolve()
    env = os.environ.get("WORKSPACE_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_WORKSPACE.resolve()


WORKSPACE = _resolve_workspace(None)
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Custom models persistence
CUSTOM_MODELS_PATH = WORKSPACE / "custom_models.json"
PRESET_OVERRIDES_PATH = WORKSPACE / "preset_overrides.json"

# Pipelines persistence
PIPELINES_PATH = WORKSPACE / "pipelines.json"


def _maybe_migrate_from_old_default():
    """一次性迁移：如果新的持久化工作空间为空，而旧 /tmp 默认目录有数据，则自动复制。"""
    if not OLD_DEFAULT_WORKSPACE.exists():
        return
    old_pipelines = OLD_DEFAULT_WORKSPACE / "pipelines.json"
    if not old_pipelines.exists():
        return
    if PIPELINES_PATH.exists():
        return
    try:
        for item in OLD_DEFAULT_WORKSPACE.iterdir():
            dest = WORKSPACE / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        print(f"[MIGRATE] 已从旧临时工作空间迁移数据: {OLD_DEFAULT_WORKSPACE} -> {WORKSPACE}")
    except Exception as e:
        print(f"[MIGRATE WARNING] 迁移旧数据失败: {e}")

# Thread-safe model state
_models_lock = threading.Lock()
_pipelines_lock = threading.Lock()

AUTH_EXEMPT_PATHS = frozenset({"/api/health", "/api/version", "/api/auth/config"})


def _mask_api_key(key: str) -> str:
    key = key or ""
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****" if key else ""


def _sanitize_model_for_client(model_cfg: dict) -> dict:
    d = {k: v for k, v in model_cfg.items() if k not in ("api_key", "fst_attr_rmrk")}
    d["api_key_masked"] = _mask_api_key(model_cfg.get("api_key", ""))
    d["has_api_key"] = bool((model_cfg.get("api_key") or "").strip())
    return d


@app.before_request
def _require_api_auth():
    if not APP_AUTH_TOKEN:
        return None
    if not request.path.startswith("/api/"):
        return None
    if request.path in AUTH_EXEMPT_PATHS:
        return None
    auth = (request.headers.get("Authorization") or "").strip()
    if auth == f"Bearer {APP_AUTH_TOKEN}":
        return None
    return jsonify({"status": "error", "error": "未授权访问"}), 401


EXTRACT_STYLE_RULES = {
    "标准萃取": {
        "temperature": 0.25,
        "max_tokens": 102400,
        "min_items": 8,
        "max_items": 22,
        "prompt_hint": "平衡覆盖核心规则、流程与经验，优先可执行条目。",
    },
    "深度萃取": {
        "temperature": 0.35,
        "max_tokens": 102400,
        "min_items": 12,
        "max_items": 40,
        "prompt_hint": "优先完整覆盖，尽量补全触发条件、判断逻辑、反模式与证据字段。",
    },
    "精简萃取": {
        "temperature": 0.15,
        "max_tokens": 102400,
        "min_items": 5,
        "max_items": 10,
        "prompt_hint": "只保留高价值高置信条目，减少冗余与重复。",
    },
}

REVISION_STYLE_RULES = {
    "标准修订": {
        "temperature": 0.25,
        "max_actions": 40,
        "allowed_actions": {"modify", "supplement", "add", "delete"},
        "prompt_hint": "平衡修订：采纳明确建议，同时保持原有合理内容。",
    },
    "严格修订": {
        "temperature": 0.1,
        "max_actions": 20,
        "allowed_actions": {"modify", "supplement"},
        "prompt_hint": "保守修订：仅处理证据充分、定位明确的修改/补充，禁止新增和删除。",
    },
    "宽松修订": {
        "temperature": 0.35,
        "max_actions": 80,
        "allowed_actions": {"modify", "supplement", "add", "delete"},
        "prompt_hint": "积极修订：尽可能采纳专家建议，允许新增与删除。",
    },
}


# Configure structured logging
_logger = logging.getLogger("tacit_knowledge")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(_ch)


@contextmanager
def _safe_workbook(path, read_only=True, data_only=True):
    """Context manager for openpyxl workbook — ensures proper close on exception."""
    wb = None
    try:
        wb = openpyxl.load_workbook(str(path), read_only=read_only, data_only=data_only)
        yield wb
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


# ─── Logging stubs (restored after _strip_debug_logs.py ran) ────────

def _debug_log(level, source, message, data=None):
    """Structured logging — writes to python logging module."""
    extra = json.dumps(data or {}, ensure_ascii=False, default=str)
    _logger.info("[%s] %s | %s", level, source, f"{message} {extra}")


def _agent_debug_log(run_id, level, source, message, data=None):
    """Agent debug logging."""
    extra = json.dumps(data or {}, ensure_ascii=False, default=str)
    _logger.info("[agent:%s][%s] %s | %s", run_id, level, source, f"{message} {extra}")


def _decode_text_by_filename(filename: str, raw: bytes) -> str:
    """Decode bytes by file extension, supporting TXT/MD/DOCX/PDF."""
    filename = (filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
        except Exception:
            return raw.decode("utf-8", errors="replace")

    if filename.endswith(".docx"):
        try:
            from docx import Document
            import io
            doc = Document(io.BytesIO(raw))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception:
            return raw.decode("utf-8", errors="replace")

    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text_from_file(file_obj) -> str:
    """Read text from uploaded file, supporting TXT, MD, DOCX, PDF."""
    filename = (file_obj.filename or "").lower()
    raw = file_obj.read()
    return _decode_text_by_filename(filename, raw)


def extract_text_from_path(file_path: str) -> str:
    """Read text from a cached workspace file path."""
    p = Path(file_path)
    raw = p.read_bytes()
    return _decode_text_by_filename(p.name, raw)


def _pipeline_prefers_markdown(pipeline_id: str) -> bool:
    """Whether current pipeline requested markdown-first artifacts."""
    if not pipeline_id:
        return False
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p.get("id") != pipeline_id:
                continue
            sd = p.get("step_data", {}) or {}
            if str(sd.get("step1_output_format", "")).strip().lower() == "markdown":
                return True
            form = sd.get("step1_form_data", {}) or {}
            return str(form.get("output_format", "")).strip().lower() == "markdown"
    return False


def _excel_to_markdown_file(excel_path: str | Path, md_path: str | Path, *, title: str = "") -> None:
    """Render an Excel workbook to markdown tables for user preview/download."""
    with _safe_workbook(str(excel_path)) as wb:
        lines: list[str] = []
        if title:
            lines.append(f"# {title}")
            lines.append("")
        for ws in wb.worksheets:
            lines.append(f"## 工作表：{ws.title}")
            lines.append("")
            rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
            if not rows:
                lines.append("（空表）")
                lines.append("")
                continue
            max_cols = max((len(r or ()) for r in rows), default=0)
            if max_cols <= 0:
                lines.append("（无可用列）")
                lines.append("")
                continue
            header_row = rows[0] or ()
            headers = []
            for i in range(max_cols):
                val = header_row[i] if i < len(header_row) else ""
                headers.append(str(val or "").replace("|", "\\|"))
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")
            for row in rows[1:]:
                vals = []
                row = row or ()
                for i in range(max_cols):
                    val = row[i] if i < len(row) else ""
                    s = str(val or "").replace("\n", " ").replace("|", "\\|")
                    vals.append(s)
                lines.append("| " + " | ".join(vals) + " |")
            lines.append("")
    Path(md_path).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _maybe_generate_markdown_artifact(pipeline_id: str, excel_name: str, *, md_prefix: str, title: str) -> tuple[str, str]:
    """Generate markdown artifact from excel when pipeline prefers markdown."""
    if not _pipeline_prefers_markdown(pipeline_id):
        return "", ""
    excel_path = safe_workspace_path(WORKSPACE, excel_name, must_exist=True)
    if not excel_path:
        return "", ""
    stem_id = uuid.uuid4().hex[:8]
    md_name = f"{md_prefix}_{stem_id}.md"
    md_path = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(md_name) or "step2", md_name)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _excel_to_markdown_file(excel_path, md_path, title=title)
        return md_name, f"/downloads/{md_name}"
    except Exception:
        return "", ""


# ─── LLM Config Helpers ──────────────────────────────────────────


def _extract_balanced_json_slice(text: str, open_ch: str, close_ch: str) -> str:
    """Extract first balanced [...] or {...} slice, respecting quoted strings."""
    start = text.find(open_ch)
    if start < 0:
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def _repair_json_text(text: str) -> str:
    """Best-effort fixes for common LLM JSON mistakes."""
    if not text:
        return text
    t = text.strip()
    t = t.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # Remove trailing commas before } or ]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return t


def _extract_json_from_text(text: str) -> str:
    """Extract JSON string from LLM response that may contain markdown code blocks."""
    text = (text or "").strip()
    if not text:
        return ""
    # Try markdown code blocks first
    for marker in ["```json", "```"]:
        if marker in text:
            parts = text.split(marker, 1)
            if len(parts) > 1:
                inner = parts[1].split("```", 1)[0].strip()
                if inner:
                    text = inner
                    break
    text = text.strip()
    if text.startswith("["):
        slice_text = _extract_balanced_json_slice(text, "[", "]")
        return slice_text or text
    if text.startswith("{"):
        slice_text = _extract_balanced_json_slice(text, "{", "}")
        return slice_text or text
    # Preamble before JSON array/object (common with custom templates)
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        slice_text = _extract_balanced_json_slice(text, open_ch, close_ch)
        if slice_text:
            return slice_text
    return text


def _items_from_parsed_root(parsed) -> list | None:
    """Normalize parsed JSON root to a list of item dicts."""
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return None
    for key in (
        "items", "data", "results", "result", "entries", "knowledge",
        "knowledge_items", "extracted", "extracted_items", "知识", "知识条目", "条目",
    ):
        val = parsed.get(key)
        if isinstance(val, list):
            return val
    return None


def _extract_top_level_json_objects(text: str) -> list[str]:
    """Extract complete top-level JSON objects from possibly truncated text."""
    objects = []
    depth = 0
    in_str = False
    esc = False
    start = -1
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
            continue
        if ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    objects.append(text[start:i + 1])
                    start = -1
    return objects


def _parse_extracted_items(raw_text: str) -> tuple[list, str]:
    """Parse LLM extraction output with robust fallbacks."""
    cleaned = _extract_json_from_text(raw_text or "")
    if not cleaned.strip():
        return [], "empty"

    for candidate in (cleaned, _repair_json_text(cleaned)):
        if not candidate.strip():
            continue
        try:
            parsed = json.loads(candidate)
            items = _items_from_parsed_root(parsed)
            if items is not None:
                return items, "json_list" if isinstance(parsed, list) else "json_items"
        except Exception:
            pass

    # JSONL: one object per line
    line_items = []
    for line in cleaned.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(_repair_json_text(line))
            if isinstance(obj, dict):
                line_items.append(obj)
        except Exception:
            continue
    if line_items:
        return line_items, "jsonl"

    # Fallback: recover complete objects from truncated/dirty output.
    recovered = []
    for obj_text in _extract_top_level_json_objects(_repair_json_text(cleaned)):
        try:
            obj = json.loads(obj_text)
            if isinstance(obj, dict):
                recovered.append(obj)
        except Exception:
            continue
    if recovered:
        return recovered, "object_recovery"

    # Last resort: scan full raw text for embedded objects
    for obj_text in _extract_top_level_json_objects(raw_text or ""):
        try:
            obj = json.loads(_repair_json_text(obj_text))
            if isinstance(obj, dict):
                recovered.append(obj)
        except Exception:
            continue
    if recovered:
        return recovered, "object_recovery"

    return [], "parse_failed"


def _align_item_keys_to_template(item: dict, target_columns: list[str]) -> dict:
    """Map LLM keys (e.g. 具体方法) to template composite keys (环节-具体方法)."""
    if not isinstance(item, dict) or not target_columns:
        return item
    out = dict(item)
    col_norm = {c: c.replace(" ", "") for c in target_columns}
    for col in target_columns:
        if col in out and str(out.get(col) or "").strip():
            continue
        parts = [p.strip() for p in col.replace("：", ":").split("-") if p.strip()]
        suffix = parts[-1] if parts else col
        for k, v in item.items():
            if v is None or isinstance(v, (dict, list)):
                continue
            kn = str(k).replace(" ", "")
            if kn == col.replace(" ", "") or kn == suffix.replace(" ", "") or suffix in str(k):
                out[col] = v
                break
    return out


def _normalize_extracted_items(items: list, target_columns: list[str]) -> list:
    normalized = []
    for raw in items or []:
        if isinstance(raw, dict):
            normalized.append(_align_item_keys_to_template(raw, target_columns))
        elif isinstance(raw, (str, int, float, bool)):
            normalized.append({"content": str(raw)})
    return normalized


def _normalize_stage_values(records: list, stage_chain: list[str]) -> list:
    """将 LLM 输出的「步骤」字段规范化到模板定义的阶段链之一（去掉数字前缀）。

    若 LLM 把「知识分类」值误填入「步骤」，则将其移到「知识分类」字段并清空步骤。
    """
    if not stage_chain:
        return records
    import re

    # 去掉阶段链中的数字前缀，建立 原始阶段 -> 规范阶段 映射
    def _clean_stage(s: str) -> str:
        return re.sub(r"^\d+[.．、\s]+", "", str(s).strip())

    canonical_stages = [_clean_stage(s) for s in stage_chain]
    stage_aliases: dict[str, str] = {}
    for raw, clean in zip(stage_chain, canonical_stages):
        stage_aliases[raw] = clean
        stage_aliases[clean] = clean
        # 数字前缀别名
        num = re.match(r"^(\d+)", raw)
        if num:
            stage_aliases[num.group(1)] = clean
            stage_aliases[f"{num.group(1)}.{clean}"] = clean
            stage_aliases[f"{num.group(1)}、{clean}"] = clean

    stage_keys = {"步骤", "stage", "step", "阶段"}
    category_keys = {"知识分类", "category", "知识类型", "分类"}

    for rec in records:
        if not isinstance(rec, dict):
            continue
        for key in list(rec.keys()):
            if key in stage_keys or any(m in key for m in stage_keys):
                val = str(rec.get(key, "")).strip()
                if not val:
                    continue
                if val in stage_aliases:
                    rec[key] = stage_aliases[val]
                else:
                    # LLM 可能把分类/标签值误填到「步骤」，迁移到「知识分类」
                    rec[key] = ""
                    for cat_key in category_keys:
                        if cat_key not in rec or not str(rec.get(cat_key, "")).strip():
                            rec[cat_key] = val
                            break
    return records


def load_preset_overrides():
    """Load runtime overrides for preset models (by name)."""
    if not PRESET_OVERRIDES_PATH.exists():
        return {}
    try:
        with open(str(PRESET_OVERRIDES_PATH), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def save_preset_overrides(overrides):
    """Persist preset model overrides."""
    with open(str(PRESET_OVERRIDES_PATH), "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)


def load_base_presets():
    """Load preset definitions from YAML + optional local secrets file."""
    if not LLM_CONFIG_PATH.exists():
        return []
    with open(str(LLM_CONFIG_PATH), "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    presets = [dict(m) for m in cfg.get("presets", [])]
    if LLM_CONFIG_LOCAL_PATH.exists():
        with open(str(LLM_CONFIG_LOCAL_PATH), "r", encoding="utf-8") as f:
            local_cfg = yaml.safe_load(f) or {}
        local_by_name = local_cfg.get("presets") or {}
        if isinstance(local_by_name, dict):
            for entry in presets:
                name = entry.get("name")
                if name and name in local_by_name:
                    override = local_by_name[name]
                    if isinstance(override, dict):
                        entry.update(override)
    return presets


def load_llm_config():
    """Load presets from YAML + overrides + custom models from JSON."""
    models = []
    overrides = load_preset_overrides()
    for m in load_base_presets():
        entry = dict(m)
        if entry.get("name") in overrides:
            entry.update(overrides[entry["name"]])
        if entry.get("url"):
            api_type = (entry.get("api_type") or API_TYPE_OPENAI).strip().lower()
            entry["url"] = normalize_llm_url(entry["url"], api_type)
        entry["is_preset"] = True
        models.append(entry)
    custom = []
    if CUSTOM_MODELS_PATH.exists():
        try:
            with open(str(CUSTOM_MODELS_PATH), "r", encoding="utf-8") as f:
                custom = json.load(f)
        except (json.JSONDecodeError, IOError):
            custom = []
    for m in custom:
        entry = dict(m)
        if entry.get("url"):
            api_type = (entry.get("api_type") or API_TYPE_OPENAI).strip().lower()
            entry["url"] = normalize_llm_url(entry["url"], api_type)
        entry["is_preset"] = False
        models.append(entry)
    return models


def save_custom_models(custom_list):
    """Persist custom models list to JSON."""
    # Strip runtime keys before saving
    clean = []
    for m in custom_list:
        d = {k: v for k, v in m.items() if k != "is_preset"}
        clean.append(d)
    with open(str(CUSTOM_MODELS_PATH), "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


def get_model_by_name(name):
    """Find a model config by name."""
    for m in load_llm_config():
        if m["name"] == name:
            return m
    return None


# ─── Static File Serving ──────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")

@app.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(str(FRONTEND_DIR / "css"), filename)

@app.route("/js/<path:filename>")
def js(filename):
    return send_from_directory(str(FRONTEND_DIR / "js"), filename)

@app.route("/vendor/<path:filename>")
def vendor_static(filename):
    """Luckysheet / jQuery 等离线静态资源（内网部署）"""
    return send_from_directory(str(FRONTEND_DIR / "vendor"), filename)

@app.route("/downloads/<path:filename>")
def downloads(filename):
    base = basename_only(filename)
    if not is_download_allowed(base):
        return jsonify({"status": "error", "error": "不允许下载该文件"}), 403

    pipeline_id = request.args.get("pipeline_id", "") or request.form.get("pipeline_id", "")
    from pipeline_artifacts import locate_workspace_file
    path = locate_workspace_file(WORKSPACE, base, pipeline_id=pipeline_id or None)
    if not path:
        return jsonify({"status": "error", "error": "文件不存在"}), 404
    return send_from_directory(str(path.parent), path.name, as_attachment=True)


@app.route("/api/files/read", methods=["GET"])
def api_file_read():
    """Read a file from workspace and return its content as text."""
    file_name = request.args.get("file_name", "")
    if not file_name:
        return jsonify({"status": "error", "error": "缺少 file_name 参数"})
    # Security: prevent path traversal
    file_name = basename_only(file_name)
    if file_name in PROTECTED_WORKSPACE_FILES or not is_download_allowed(file_name):
        return jsonify({"status": "error", "error": "不允许读取该文件"})
    file_path = safe_workspace_path(WORKSPACE, file_name, must_exist=True)
    if not file_path:
        return jsonify({"status": "error", "error": f"文件不存在: {file_name}"})
    try:
        with open(str(file_path), "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"status": "ok", "content": content, "file_name": file_name})
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取失败: {str(e)}"})


@app.route("/api/files/save", methods=["POST"])
def api_file_save():
    """Save text content to a file in workspace."""
    data = request.get_json(force=True)
    file_name = (data.get("file_name") or "").strip()
    content = data.get("content", "")
    if not file_name:
        return jsonify({"status": "error", "error": "缺少 file_name 参数"})
    # Security: prevent path traversal
    file_name = basename_only(file_name)
    if file_name in PROTECTED_WORKSPACE_FILES or not is_download_allowed(file_name):
        return jsonify({"status": "error", "error": "不允许写入该文件"})
    file_path = safe_workspace_path(WORKSPACE, file_name, must_exist=False)
    if not file_path:
        return jsonify({"status": "error", "error": "非法文件路径"})
    try:
        with open(str(file_path), "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"status": "ok", "file_name": file_name, "size": len(content)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"保存失败: {str(e)}"})


@app.route("/api/files/cache_upload", methods=["POST"])
def api_file_cache_upload():
    """Cache uploaded source file in workspace, return cached filename."""
    file_obj = request.files.get("file")
    pipeline_id = request.form.get("pipeline_id", "").strip()
    step = request.form.get("step", "").strip()
    if not file_obj or not file_obj.filename:
        return jsonify({"status": "error", "error": "缺少上传文件"})

    try:
        saved_path = save_upload(file_obj, prefix=f"cache_s{step or 'x'}")
        base = os.path.basename(saved_path)
        resp = {"status": "ok", "file_name": base}

        if pipeline_id and step in {"2", "3"}:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        sd = p.setdefault("step_data", {})
                        sd[f"step{step}_cached_file"] = base
                        sd[f"step{step}_cached_name"] = file_obj.filename
                        save_pipelines(pipelines)
                        break
        return jsonify(resp)
    except Exception as e:
        return jsonify({"status": "error", "error": f"缓存上传失败: {str(e)}"})


# ─── Health Check ─────────────────────────────────────────────────

@app.route("/api/frontend/vendor-check")
def api_frontend_vendor_check():
    """检查 Excel 在线编辑所需静态资源是否存在（内网部署自检）"""
    checks = {
        "vendor_route": True,
        "files": {},
    }
    paths = {
        "plugin_js": FRONTEND_DIR / "vendor" / "luckysheet" / "plugins" / "js" / "plugin.js",
        "luckysheet_umd": FRONTEND_DIR / "vendor" / "luckysheet" / "luckysheet.umd.js",
    }
    all_ok = True
    for key, p in paths.items():
        exists = p.is_file()
        checks["files"][key] = {"path": str(p), "exists": exists}
        if not exists:
            all_ok = False
    checks["ok"] = all_ok
    checks["hint"] = (
        "就绪"
        if all_ok
        else "缺少 frontend/vendor，请执行: node scripts/copy-frontend-vendor.js"
    )
    return jsonify(checks)



@app.route("/api/auth/config", methods=["GET"])
def api_auth_config():
    return jsonify({"status": "ok", "auth_required": bool(APP_AUTH_TOKEN)})


@app.route("/api/build_info", methods=["GET"])
def api_build_info():
    info = get_release_info()
    return jsonify({
        "status": "ok",
        "step2_excel": True,
        **info,
    })


@app.route("/api/version", methods=["GET"])
def api_version():
    """标准版本查询（内网部署识别 / 升级比对）。"""
    return jsonify({"status": "ok", **get_release_info()})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", **get_release_info()})


# ─── Helper: run script and capture JSON output ──────────────────

def run_script(script_name, args_list):
    """Run a script in scripts/ directory and return parsed JSON from stdout."""
    script_path = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script_path)] + args_list
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_DIR)
        )
        # 优先尝试从 stdout 解析 JSON（即使 returncode != 0）
        stdout = result.stdout.strip()
        if stdout:
            lines = [l for l in stdout.split("\n") if l.strip()]
            for line in reversed(lines):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        # 如果 stdout 无可解析 JSON，返回 stderr 或通用错误
        stderr = result.stderr.strip()
        if result.returncode != 0:
            return {"status": "error", "error": stderr or f"Exit code {result.returncode}"}
        if not stdout:
            return {"status": "error", "error": "脚本无输出"}
        return {"status": "error", "error": f"无法解析脚本输出: {stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "脚本执行超时(120s)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def save_upload(file_obj, prefix="upload"):
    """Save an uploaded file to workspace, return the path."""
    ext = Path(file_obj.filename).suffix if file_obj.filename else ".xlsx"
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
    fpath = WORKSPACE / fname
    file_obj.save(str(fpath))
    return str(fpath)


# ─── Pipeline Management ──────────────────────────────────────────


def load_pipelines():
    """Load pipelines from JSON file, return list."""
    if PIPELINES_PATH.exists():
        try:
            with open(str(PIPELINES_PATH), "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_pipelines(pipelines):
    """Persist pipelines list to JSON."""
    with open(str(PIPELINES_PATH), "w", encoding="utf-8") as f:
        json.dump(pipelines, f, ensure_ascii=False, indent=2)


@app.route("/api/pipelines", methods=["GET"])
def api_list_pipelines():
    """List all pipelines, newest first."""
    with _pipelines_lock:
        pipelines = load_pipelines()
    pipelines.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return jsonify({"status": "ok", "pipelines": pipelines})


@app.route("/api/pipelines", methods=["POST"])
def api_create_pipeline():
    """Create a new pipeline."""
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    scenario = (data.get("scenario") or "").strip()
    domain = (data.get("domain") or "").strip()

    if not name:
        return jsonify({"status": "error", "error": "流水线名称不能为空"})

    now = datetime.datetime.now().isoformat()
    pipeline = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "scenario": scenario,
        "domain": domain or scenario,
        "current_step": 1,
        "step_status": {
            "1": "pending",
            "2": "pending",
            "3": "pending",
            "4": "pending",
            "5": "pending",
        },
        "step_data": {},
        "created_at": now,
        "updated_at": now,
    }

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipelines.append(pipeline)
        save_pipelines(pipelines)

    return jsonify({"status": "ok", "pipeline": pipeline})


@app.route("/api/pipelines/<pipeline_id>", methods=["GET"])
def api_get_pipeline(pipeline_id):
    """Get a single pipeline by ID."""
    with _pipelines_lock:
        pipelines = load_pipelines()
    for p in pipelines:
        if p["id"] == pipeline_id:
            return jsonify({"status": "ok", "pipeline": p})
    return jsonify({"status": "error", "error": "流水线不存在"})


@app.route("/api/pipelines/<pipeline_id>", methods=["PUT"])
def api_update_pipeline(pipeline_id):
    """Update a pipeline's step status/data."""
    data = request.get_json(force=True)

    with _pipelines_lock:
        pipelines = load_pipelines()
        target = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                target = p
                break
        if not target:
            return jsonify({"status": "error", "error": "流水线不存在"})

        if "current_step" in data:
            target["current_step"] = max(target.get("current_step", 1), data["current_step"])
        if "step_status" in data:
            for k, v in data["step_status"].items():
                if v == "done" or target["step_status"].get(k) != "done":
                    target["step_status"][k] = v
        if "step_data" in data:
            patch = data["step_data"]
            if not isinstance(patch, dict):
                return jsonify({"status": "error", "error": "step_data 格式错误"})
            err = validate_step_data_patch(patch)
            if err:
                return jsonify({"status": "error", "error": err})
            target["step_data"].update(patch)
        if "name" in data:
            target["name"] = data["name"]

        target["updated_at"] = datetime.datetime.now().isoformat()

        save_pipelines(pipelines)

    return jsonify({"status": "ok", "pipeline": target})


@app.route("/api/pipelines/<pipeline_id>", methods=["DELETE"])
def api_delete_pipeline(pipeline_id):
    """Delete a pipeline."""
    with _pipelines_lock:
        pipelines = load_pipelines()
        before = len(pipelines)
        pipelines = [p for p in pipelines if p["id"] != pipeline_id]
        if len(pipelines) == before:
            return jsonify({"status": "error", "error": "流水线不存在"})
        save_pipelines(pipelines)

    return jsonify({"status": "ok"})


@app.route("/api/pipelines/<pipeline_id>/clear", methods=["POST"])
def api_clear_pipeline(pipeline_id):
    """Clear a pipeline's step data and reset all steps to pending."""
    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return jsonify({"status": "error", "error": "流水线不存在"})
        pipeline["step_data"] = {}
        pipeline["step_status"] = {str(i): "pending" for i in range(1, 6)}
        pipeline["current_step"] = 1
        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)
    return jsonify({"status": "ok"})


@app.route("/api/pipelines/<pipeline_id>/rollback/<int:step>", methods=["POST"])
def api_rollback_pipeline(pipeline_id, step):
    """Roll back a pipeline to a previous step; reset downstream step status and outputs."""
    if step < 1 or step > 5:
        return jsonify({"status": "error", "error": "步骤号必须在 1-5 之间"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return jsonify({"status": "error", "error": "流水线不存在"})

        for s in range(step, 6):
            pipeline["step_status"][str(s)] = "pending"

        sd = pipeline.setdefault("step_data", {})
        keys = keys_to_clear_from_step(step)

        # 将下游产出文件移入 _trash（不直接删除，便于追溯）
        from pipeline_artifacts import downstream_output_keys, auxiliary_step_data_keys
        _trash_dir = WORKSPACE / "_trash"
        for key in downstream_output_keys(step):
            filename = str(sd.get(key, "")).strip()
            if not filename:
                continue
            from pipeline_artifacts import locate_workspace_file
            file_path = locate_workspace_file(WORKSPACE, filename, pipeline_id=pipeline_id)
            if file_path and file_path.exists():
                try:
                    _trash_dir.mkdir(parents=True, exist_ok=True)
                    dest = _trash_dir / file_path.name
                    if dest.exists():
                        dest = _trash_dir / f"{file_path.stem}_{uuid.uuid4().hex[:6]}{file_path.suffix}"
                    shutil.move(str(file_path), str(dest))
                except Exception:
                    pass
            sd.pop(key, None)

        for key in auxiliary_step_data_keys(step):
            sd.pop(key, None)

        pipeline["current_step"] = step

        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)

    return jsonify({"status": "ok", "pipeline": pipeline})


# ─── Step 1: Generate Template ────────────────────────────────────

@app.route("/api/step1/schema", methods=["GET"])
def api_step1_schema():
    """返回当前知识结构方案（scenario-schema.yaml）摘要，供 Step1 界面展示。"""
    from scenario_schema import load_scenario_schema, schema_summary

    if not SCHEMA_PATH.exists():
        return jsonify({"status": "error", "error": "未找到 scenario-schema.yaml"})
    schema = load_scenario_schema(SCHEMA_PATH)
    return jsonify({
        "status": "ok",
        "schema": schema_summary(schema, schema_path=SCHEMA_PATH),
    })


@app.route("/api/step1/templates", methods=["GET"])
def api_step1_templates():
    """列出 Step1 模板来源：默认 schema + 可选 legacy Excel 模板。"""
    from scenario_schema import load_scenario_schema, schema_summary
    from step1_template import list_default_step1_templates, find_default_step1_template

    schema_info = {}
    if SCHEMA_PATH.exists():
        schema_info = schema_summary(load_scenario_schema(SCHEMA_PATH), schema_path=SCHEMA_PATH)

    step1_tpl_dir = SAMPLES_DIR / "step1-场景锚定"
    all_templates = list_default_step1_templates(step1_tpl_dir)
    templates = all_templates  # 默认返回所有有效 legacy 模板，不再只过滤"测试"
    default_tpl = find_default_step1_template(step1_tpl_dir)
    legacy_default = default_tpl.name if default_tpl else ""

    return jsonify({
        "status": "ok",
        "schema": schema_info,
        "default_mode": "schema",
        "templates": [
            {"name": p.name, "label": p.stem, "kind": "legacy"}
            for p in templates
        ],
        "default_template": "__schema__",
        "legacy_default_template": legacy_default,
    })


@app.route("/api/step1/generate", methods=["POST"])
def api_step1_generate():
    """Step1: 将场景四项填入萃取模板前四列，保留模板表结构（无 LLM）。"""
    from step1_template import (
        fill_scenario_skeleton,
        find_default_step1_template,
        list_default_step1_templates,
    )
    from scenario_schema import (
        enrich_knowledge_columns_for_markdown,
        load_scenario_schema,
        normalize_knowledge_columns,
        resolve_knowledge_columns_for_request,
    )
    from step1_markdown_builder import generate_markdown_skeleton
    from step1_schema_builder import generate_skeleton_from_schema

    scenario_name = request.form.get("scenario_name", "").strip()
    scenario_content = request.form.get("scenario_content", "").strip()
    sub_scenarios_json = request.form.get("sub_scenarios", "[]")
    pipeline_id = request.form.get("pipeline_id", "") or request.args.get("pipeline_id", "")
    template_mode = (request.form.get("template_mode", "") or "").strip().lower()
    output_format = (request.form.get("output_format", "excel") or "excel").strip().lower()
    if output_format not in {"excel", "markdown"}:
        output_format = "excel"
    knowledge_columns_json = request.form.get("knowledge_columns", "[]")

    if not scenario_name:
        return jsonify({"status": "error", "error": "场景名称不能为空"})
    _debug_log(
        "H1",
        "app_server.py:api_step1_generate",
        "step1 request received",
        {
            "has_pipeline_id": bool(pipeline_id),
            "sub_scenarios_json_len": len(sub_scenarios_json or ""),
            "template_mode": template_mode or "schema",
            "output_format": output_format,
        },
    )

    try:
        sub_scenarios = json.loads(sub_scenarios_json) if sub_scenarios_json else []
    except json.JSONDecodeError:
        sub_scenarios = []

    try:
        user_columns_raw = json.loads(knowledge_columns_json) if knowledge_columns_json else []
        if not isinstance(user_columns_raw, list):
            user_columns_raw = []
    except json.JSONDecodeError:
        user_columns_raw = []

    schema = load_scenario_schema(SCHEMA_PATH) if SCHEMA_PATH.exists() else {}
    knowledge_columns = resolve_knowledge_columns_for_request(schema, user_columns_raw)
    has_custom_columns = bool(normalize_knowledge_columns(user_columns_raw))
    columns_enriched = False
    user_knowledge_columns = list(knowledge_columns)
    if output_format == "markdown":
        knowledge_columns, columns_enriched, _substantive = enrich_knowledge_columns_for_markdown(
            user_columns_raw, schema
        )
    if not knowledge_columns and output_format != "upload":
        return jsonify({"status": "error", "error": "请至少定义一列知识字段"})

    template_path = None
    selected_default_template = request.form.get("default_template", "").strip()
    template_source = "schema"
    template_name = ""
    schema_meta = None
    md_name = ""
    md_download_url = ""
    upload = request.files.get("template")
    if upload and upload.filename:
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in (".xlsx", ".xls"):
            return jsonify({"status": "error", "error": "模板仅支持 .xlsx / .xls 格式"})
        temp_name = f"upload_tpl_{uuid.uuid4().hex[:8]}{ext}"
        template_path_obj = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(temp_name) or "uploads", temp_name)
        template_path_obj.parent.mkdir(parents=True, exist_ok=True)
        template_path = str(template_path_obj)
        upload.save(template_path)
        template_source = "upload"
        template_name = upload.filename
    elif template_mode == "legacy" and not has_custom_columns:
        step1_tpl_dir = SAMPLES_DIR / "step1-场景锚定"
        default_tpl = None
        if selected_default_template and selected_default_template != "__schema__":
            candidates = {p.name: p for p in list_default_step1_templates(step1_tpl_dir)}
            default_tpl = candidates.get(selected_default_template)
            if not default_tpl:
                return jsonify({"status": "error", "error": "所选 Excel 模板不存在，请刷新后重试"})
        else:
            default_tpl = find_default_step1_template(step1_tpl_dir)

        if default_tpl:
            template_path = str(default_tpl)
            template_source = "legacy"
            template_name = default_tpl.name

    uid = uuid.uuid4().hex[:8]
    output_name = f"template_{uid}.xlsx"
    output_path_obj = workspace_path_for(WORKSPACE, pipeline_id, "step1", output_name)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path = str(output_path_obj)
    primary_download_name = output_name
    primary_download_url = "/downloads/" + output_name

    try:
        if template_path and os.path.exists(template_path):
            fill_result = fill_scenario_skeleton(
                template_path, output_path, scenario_name, scenario_content, sub_scenarios
            )
            knowledge_columns = knowledge_columns or []
            if output_format == "markdown":
                md_name = f"template_{uid}.md"
                md_path = workspace_path_for(WORKSPACE, pipeline_id, "step1", md_name)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                _excel_to_markdown_file(output_path, md_path, title=f"场景锚定骨架 · {scenario_name}")
                primary_download_name = md_name
                primary_download_url = "/downloads/" + md_name
                md_download_url = primary_download_url
                if template_source == "upload":
                    template_source = "upload_markdown"
                elif template_source == "legacy":
                    template_source = "legacy_markdown"
        elif output_format == "markdown":
            if not SCHEMA_PATH.exists():
                return jsonify({
                    "status": "error",
                    "error": "未找到 config/scenario-schema.yaml，无法生成骨架",
                })
            md_name = f"template_{uid}.md"
            md_path_obj = workspace_path_for(WORKSPACE, pipeline_id, "step1", md_name)
            md_path_obj.parent.mkdir(parents=True, exist_ok=True)
            md_path = str(md_path_obj)
            generate_markdown_skeleton(
                md_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns,
            )
            fill_result = generate_skeleton_from_schema(
                SCHEMA_PATH,
                output_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns=knowledge_columns,
            )
            schema_meta = fill_result.get("schema") or {}
            template_source = "schema_markdown"
            template_name = "自定义列 · Markdown + Excel"
            primary_download_name = md_name
            primary_download_url = "/downloads/" + md_name
            md_download_url = primary_download_url
        else:
            if not SCHEMA_PATH.exists():
                return jsonify({
                    "status": "error",
                    "error": "未找到 config/scenario-schema.yaml，无法按结构方案生成模板",
                })
            fill_result = generate_skeleton_from_schema(
                SCHEMA_PATH,
                output_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns=knowledge_columns,
            )
            schema_meta = fill_result.get("schema") or {}
            template_source = "schema"
            template_name = (
                f"{schema_meta.get('display_name', '自定义结构')} "
                f"({schema_meta.get('version', 'v1.0')})"
            ).strip()
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"生成场景骨架失败: {str(e)}"})

    if schema_meta is None and SCHEMA_PATH.exists():
        from scenario_schema import schema_summary
        schema_meta = schema_summary(schema, schema_path=SCHEMA_PATH)
        schema_meta["knowledge_columns"] = knowledge_columns

    result = {
        "status": "ok",
        "scenario": scenario_name,
        "download_url": primary_download_url,
        "file_name": primary_download_name,
        "excel_file": output_name,
        "excel_download_url": "/downloads/" + output_name,
        "output_format": output_format,
        "knowledge_columns": knowledge_columns,
        "user_knowledge_columns": user_knowledge_columns,
        "columns_enriched": columns_enriched,
        "version": (schema_meta or {}).get("version", "v0.1"),
        "fields_info": fill_result.get("fields_info", []),
        "sub_scenario_count": fill_result.get("sub_scenario_count", len(sub_scenarios)),
        "template_source": template_source,
        "template_name": template_name,
        "schema": schema_meta,
    }
    if md_name:
        result["markdown_file"] = md_name
        result["markdown_download_url"] = md_download_url

    # 保存到 pipeline step_data
    saved_pipeline = None
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    for key in keys_to_clear_from_step(1):
                        sd.pop(key, None)
                    sd["step1_output_file"] = output_name
                    sd["step1_download_url"] = "/downloads/" + output_name
                    sd["step1_template_source"] = template_source
                    sd["step1_template_name"] = template_name
                    sd["step1_output_format"] = output_format
                    sd["step1_knowledge_columns"] = knowledge_columns
                    sd["step1_user_knowledge_columns"] = user_knowledge_columns
                    sd["step1_columns_enriched"] = columns_enriched
                    if md_name:
                        sd["step1_md_file"] = md_name
                        sd["step1_md_download_url"] = md_download_url
                    else:
                        sd.pop("step1_md_file", None)
                        sd.pop("step1_md_download_url", None)
                    p["scenario"] = scenario_name
                    p["domain"] = p.get("domain", "") or scenario_name
                    p.setdefault("step_status", {})
                    p["step_status"]["1"] = "done"
                    if "2" not in p["step_status"] or p["step_status"]["2"] == "pending":
                        p["step_status"]["2"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 2)
                    p["updated_at"] = datetime.datetime.now().isoformat()
                    save_pipelines(pipelines)
                    saved_pipeline = dict(p)
                    saved_pipeline["step_data"] = dict(p.get("step_data", {}))
                    break

    if saved_pipeline:
        result["pipeline"] = saved_pipeline
    return jsonify(result)


# ─── Step 2: Get Step 1 Output ─────────────────────────────────────

@app.route("/api/step2/prev_output", methods=["GET"])
def api_step2_prev_output():
    """获取当前流水线 Step1 的输出件信息，供 Step2 引用"""
    pipeline_id = request.args.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                # Deep copy to avoid race conditions after lock release
                pipeline = dict(p)
                pipeline["step_data"] = dict(p.get("step_data", {}))
                break

    if not pipeline:
        return jsonify({"status": "error", "error": "流水线不存在"})

    step_data = pipeline.get("step_data", {})
    step1_file = step_data.get("step1_output_file", "")
    step1_url = step_data.get("step1_download_url", "")
    step1_md_file = step_data.get("step1_md_file", "")
    step1_md_url = step_data.get("step1_md_download_url", "")

    if not step1_file:
        return jsonify({
            "status": "ok",
            "has_output": False,
            "hint": "请先在「场景锚定」生成场景骨架（需已创建并进入流水线）",
        })

    from pipeline_artifacts import locate_workspace_file
    resolved = locate_workspace_file(WORKSPACE, step1_file, pipeline_id=pipeline_id)
    file_path = str(resolved) if resolved else ""
    if not file_path or not os.path.exists(file_path):
        return jsonify({
            "status": "ok",
            "has_output": False,
            "hint": "场景骨架文件已丢失，请回到场景锚定重新生成",
        })

    # Read Excel template structure for context
    fields_info = []
    if os.path.exists(file_path):
        try:
            with _safe_workbook(file_path) as wb:
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    headers = []
                    for cell in next(ws.iter_rows(min_row=1, max_row=1), []):
                        if cell.value:
                            headers.append(str(cell.value))
                    if headers:
                        fields_info.append({"sheet": sheet_name, "headers": headers})
        except Exception:
            pass

    return jsonify({
        "status": "ok",
        "has_output": True,
        "file_name": step1_file,
        "download_url": step1_url,
        "markdown_file": step1_md_file,
        "markdown_download_url": step1_md_url,
        "output_format": step_data.get("step1_output_format", "excel"),
        "scenario": pipeline.get("scenario", ""),
        "domain": pipeline.get("domain", ""),
        "fields_info": fields_info,
    })


# ─── Validation (Steps 2, 3, 4) ──────────────────────────────────

# ─── Step 4: Compile ──────────────────────────────────────────────

@app.route("/api/step4/compile", methods=["POST"])
def api_step4_compile():
    """智能转化：生成思维链 / QA 对 / OpenClaw Skill 三类交付物。"""
    pipeline_id = request.form.get("pipeline_id", "")
    excel_file = request.files.get("excel")
    # region agent log
    _agent_debug_log(
        "run-2",
        "H6",
        "app_server.py:api_step4_compile:entry",
        "step4 compile request received",
        {
            "has_pipeline_id": bool(pipeline_id),
            "has_upload": bool(excel_file),
            "formats": request.form.get("formats", ""),
        },
    )
    # endregion

    input_path = None
    ir_path = None
    ir_source_key = ""
    pipeline = None
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    pipeline = dict(p)
                    pipeline["step_data"] = dict(p.get("step_data", {}))
                    break
    if pipeline_id and not excel_file and pipeline:
            step_data = pipeline.get("step_data", {})
            # 首选 Skill IR（step3_aligned_file → step2_draft_file），Excel 为过渡期回退
            ir_path, ir_source_key = resolve_knowledge_ir_path(WORKSPACE, step_data)
            if not ir_path:
                resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, step_data, purpose="compile")
                if resolved:
                    input_path = str(resolved)

    if not input_path and not ir_path:
        if excel_file:
            input_path = save_upload(excel_file, prefix="compile")
        else:
            return jsonify({
                "status": "error",
                "error": "未找到可转化的知识稿。请先完成「知识萃取」，并在「知识对齐」节点生成对齐稿（或上传确认版 Excel）",
            })
    input_basename = os.path.basename(str(ir_path)) if ir_path else os.path.basename(input_path or "")
    # region agent log
    _agent_debug_log(
        "run-2",
        "H6",
        "app_server.py:api_step4_compile:input",
        "step4 compile input resolved",
        {"input_basename": input_basename, "input_kind": "ir" if ir_path else "excel"},
    )
    # endregion
    _debug_log(
        "H5",
        "app_server.py:api_step4_compile",
        "step4 compile start",
        {"has_pipeline_id": bool(pipeline_id), "input_basename": input_basename},
    )

    from knowledge_delivery import excel_to_delivery_bundle, records_to_delivery_bundle

    output_dir_name = f"delivery_{uuid.uuid4().hex[:8]}"
    output_dir_obj = workspace_path_for(WORKSPACE, pipeline_id, "step4", output_dir_name)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    output_dir = str(output_dir_obj)
    config_path = str(SCHEMA_PATH) if SCHEMA_PATH.exists() else ""

    pipeline_ctx = {}
    source_docs: list[str] = []
    if pipeline_id and pipeline:
        sd = pipeline.get("step_data") or {}
        step1_form = sd.get("step1_form_data") or {}
        pipeline_ctx = {
            "pipeline_id": pipeline_id,
            "scenario_name": pipeline.get("scenario") or step1_form.get("scenario_name", ""),
            "scenario_content": step1_form.get("scenario_content", ""),
            "sub_scenarios": step1_form.get("sub_scenarios") or [],
            # 用于 assets/ 目录抽取上下游产物
            "step1_output_file": sd.get("step1_output_file", ""),
            "step2_output_file": sd.get("step2_output_file", ""),
            "step3_final_file": sd.get("step3_final_file", ""),
            "output_dir": str(WORKSPACE),
        }
        # 收集 references/source_document_*.txt 的候选文件
        for key in ("step1_output_file", "step2_output_file", "step3_final_file", "step3_revision_file"):
            fname = sd.get(key, "")
            if fname:
                p = safe_workspace_path(WORKSPACE, fname, must_exist=True)
                if p and str(p) not in source_docs:
                    source_docs.append(str(p))

    formats_raw = request.form.get("formats", "").strip()
    formats = [f.strip() for f in formats_raw.split(",") if f.strip()] if formats_raw else None

    published_version = 0
    try:
        if ir_path:
            from skill_ir import ir_to_records, ir_version_info, load_ir

            ir = load_ir(ir_path)
            published_version = int(ir.get("skill_meta", {}).get("draft_version", 1) or 1)
            result = records_to_delivery_bundle(
                ir_to_records(ir),
                ir_version_info(ir),
                config_path,
                output_dir,
                formats=formats,
                source_name=ir.get("skill_meta", {}).get("scenario_name", ""),
                pipeline_context=pipeline_ctx,
                source_docs=source_docs,
                ir_path=str(ir_path),
            )
            result["input_kind"] = "ir"
            result["ir_source"] = ir_source_key
            result["ir_version"] = published_version
        else:
            result = excel_to_delivery_bundle(
                input_path, config_path, output_dir, pipeline_ctx or None, formats=formats
            )
            result["input_kind"] = "excel"
    except Exception as e:
        # region agent log
        _agent_debug_log(
            "run-2",
            "H7",
            "app_server.py:api_step4_compile:exception",
            "step4 delivery generation raised exception",
            {"error": str(e)[:500], "input_basename": input_basename},
        )
        # endregion
        _debug_log(
            "H5",
            "app_server.py:api_step4_compile",
            "step4 compile exception",
            {"error": str(e)[:300]},
        )
        return jsonify({"status": "error", "error": f"智能转化失败: {str(e)}"})

    if result.get("status") != "ok":
        err = result.get("error") or result.get("message") or "智能转化失败"
        # region agent log
        _agent_debug_log(
            "run-2",
            "H7",
            "app_server.py:api_step4_compile:result_error",
            "step4 delivery generation returned error",
            {"error": str(err)[:500], "input_basename": input_basename},
        )
        # endregion
        _debug_log(
            "H5",
            "app_server.py:api_step4_compile",
            "step4 compile failed",
            {"error": str(err)[:300]},
        )
        return jsonify({"status": "error", "error": err})

    artifacts = result.get("artifacts") or {}
    downloads = {}

    def _publish_artifact(key: str, src_path: str, prefix: str, ext: str):
        if not src_path or not os.path.isfile(src_path):
            return None
        name = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
        dest = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(name) or "step4", name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, str(dest))
        info = {
            "file_name": name,
            "download_url": "/downloads/" + name,
        }
        meta = artifacts.get(key) or {}
        if meta.get("count") is not None:
            info["count"] = meta["count"]
        if meta.get("label"):
            info["label"] = meta["label"]
        downloads[key] = info
        return name, "/downloads/" + name

    cot_pub = _publish_artifact(
        "cot", (artifacts.get("cot") or {}).get("path"), "COT", ".md"
    )
    qa_pub = _publish_artifact(
        "qa", (artifacts.get("qa") or {}).get("path"), "QA", ".json"
    )
    qa_md_pub = _publish_artifact(
        "qa_md", (artifacts.get("qa") or {}).get("markdown_path"), "QA", ".md"
    )
    skill_pub = _publish_artifact(
        "skill", (artifacts.get("skill") or {}).get("path"), "SKILL", ".md"
    )
    manifest_pub = _publish_artifact(
        "openclaw_manifest",
        (artifacts.get("skill") or {}).get("manifest_path"),
        "openclaw",
        ".json",
    )
    skill_zip_pub = _publish_artifact(
        "skill_zip",
        (artifacts.get("skill") or {}).get("zip_path"),
        "SKILL_DIR",
        ".zip",
    )

    result["artifacts_download"] = downloads
    if skill_pub:
        result["download_url"] = skill_pub[1]
        result["download_name"] = skill_pub[0]
    if cot_pub:
        result["cot_download_url"] = cot_pub[1]
        result["cot_download_name"] = cot_pub[0]
    if qa_pub:
        result["qa_download_url"] = qa_pub[1]
        result["qa_download_name"] = qa_pub[0]
    if qa_md_pub:
        result["qa_md_download_url"] = qa_md_pub[1]
        result["qa_md_download_name"] = qa_md_pub[0]
    if manifest_pub:
        result["openclaw_manifest_url"] = manifest_pub[1]
        result["openclaw_manifest_name"] = manifest_pub[0]
    if skill_zip_pub:
        result["skill_dir_zip_url"] = skill_zip_pub[1]
        result["skill_dir_zip_name"] = skill_zip_pub[0]

    # 质量评分（确定性规则）→ 发布门槛判定
    quality_score = None
    can_publish = False
    try:
        if ir_path:
            from quality_report import quality_report_from_records
            from skill_ir import ir_to_records as _ir2rec, load_ir as _load_ir

            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            q = quality_report_from_records(_ir2rec(_load_ir(ir_path)), config)
            if q.get("status") == "ok":
                quality_score = q.get("total_score")
                threshold = float((config.get("quality") or {}).get("skill_score_threshold", 75))
                can_publish = bool(quality_score is not None and quality_score >= threshold)
                result["quality_score"] = quality_score
                result["quality_grade"] = q.get("grade", "")
                result["publish_threshold"] = threshold
                result["can_publish"] = can_publish
    except Exception:
        pass

    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    if skill_pub:
                        sd["step4_skill_file"] = skill_pub[0]
                        sd["step4_download_url"] = skill_pub[1]
                    if cot_pub:
                        sd["step4_cot_file"] = cot_pub[0]
                        sd["step4_cot_download_url"] = cot_pub[1]
                    if qa_pub:
                        sd["step4_qa_file"] = qa_pub[0]
                        sd["step4_qa_download_url"] = qa_pub[1]
                    if qa_md_pub:
                        sd["step4_qa_md_file"] = qa_md_pub[0]
                        sd["step4_qa_md_download_url"] = qa_md_pub[1]
                    if manifest_pub:
                        sd["step4_manifest_file"] = manifest_pub[0]
                        sd["step4_manifest_url"] = manifest_pub[1]
                    if skill_zip_pub:
                        sd["step4_skill_dir_zip_file"] = skill_zip_pub[0]
                        sd["step4_skill_dir_zip_url"] = skill_zip_pub[1]
                    if published_version:
                        sd["step4_published_version"] = published_version
                    p.setdefault("step_status", {})
                    p["step_status"]["4"] = "done"
                    if p["step_status"].get("5", "pending") == "pending":
                        p["step_status"]["5"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 4)
                    p["updated_at"] = datetime.datetime.now().isoformat()
                    save_pipelines(pipelines)
                    break
    return jsonify(result)


@app.route("/api/step4/generate-executable-skill", methods=["POST"])
def api_step4_generate_executable_skill():
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("model", "")

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    # Resolve pipeline and golden DB
    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return jsonify({"status": "error", "error": "流水线不存在"})
        pipeline = dict(pipeline)
        pipeline["step_data"] = dict(pipeline.get("step_data", {}))

    sd = pipeline.get("step_data", {})

    # Collect knowledge items from step3 output
    step3_key = sd.get("step3_final_file") or sd.get("step3_revision_file") or sd.get("step2_output_file")
    if not step3_key:
        return jsonify({"status": "error", "error": "未找到 step3 对齐输出或 step2 萃取输出"})

    step3_path = safe_workspace_path(WORKSPACE, step3_key, must_exist=True)
    if not step3_path:
        return jsonify({"status": "error", "error": f"知识稿文件不存在: {step3_key}"})

    knowledge_items = []
    try:
        with _safe_workbook(str(step3_path)) as wb:
            for ws in wb.worksheets:
                headers = [str(c.value or "") for c in next(ws.iter_rows(min_row=1, max_row=1))]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if any(v for v in row):
                        knowledge_items.append({headers[i]: str(row[i] or "") for i in range(min(len(headers), len(row)))})
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取知识稿失败: {str(e)}"})

    if not knowledge_items:
        return jsonify({"status": "error", "error": "知识稿中无有效数据行"})

    # Get golden DB schema
    from skill_generator import build_golden_schema_prompt, build_skill_generation_prompt, get_golden_stats

    golden_schema = build_golden_schema_prompt()
    golden_stats = get_golden_stats()

    # Resolve model
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        models_list = load_llm_config()
        if models_list:
            model_cfg = models_list[0]
    if not model_cfg:
        return jsonify({"status": "error", "error": "无可用 LLM 模型"})

    prompt = build_skill_generation_prompt(
        scenario_name=pipeline.get("scenario", "") or pipeline.get("name", ""),
        scenario_description=sd.get("step1_form_data", {}).get("scenario_content", "") or "",
        knowledge_items=knowledge_items,
        golden_schema=golden_schema,
    )

    try:
        result = call_llm_with_retry(
            model_cfg,
            [{"role": "user", "content": prompt}],
            max_tokens=8192,
            temperature=0.5,
        )
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
    except Exception as e:
        return jsonify({"status": "error", "error": f"LLM 调用失败: {str(e)}"})

    from skill_generator import parse_skill_output

    parsed = parse_skill_output(raw)

    # Save the generated Skill file
    slug = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "_", pipeline.get("scenario", "") or pipeline.get("name", ""))[:30]
    skill_filename = f"SKILL_{slug}_{pipeline_id[:6]}.md"
    skill_path = workspace_path_for(WORKSPACE, pipeline_id, "step4", skill_filename)
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(raw, encoding="utf-8")

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                p.setdefault("step_data", {})["step4_executable_skill_file"] = skill_filename
                p.setdefault("step_data", {})["step4_executable_skill_url"] = f"/downloads/{skill_filename}"
                save_pipelines(pipelines)
                break

    return jsonify({
        "status": "ok",
        "skill_filename": skill_filename,
        "download_url": f"/downloads/{skill_filename}",
        "frontmatter": parsed["frontmatter"],
        "section_count": parsed["section_count"],
        "has_sql": parsed["has_sql"],
        "preview": raw[:2000],
        "golden_stats": golden_stats,
    })


def _read_step3_knowledge_items(pipeline_id: str) -> tuple[list[dict], dict]:
    """Shared helper: resolve pipeline, read step3 IR/Excel, return (items, pipeline_dict)."""
    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            raise ValueError("流水线不存在")
        pipeline = dict(pipeline)
        pipeline["step_data"] = dict(pipeline.get("step_data", {}))

    sd = pipeline.get("step_data", {})

    # 首选 Skill IR（对齐版 → 萃取稿）
    ir_path, _ir_key = resolve_knowledge_ir_path(WORKSPACE, sd)
    if ir_path:
        try:
            from skill_ir import ir_to_records, load_ir
            items = ir_to_records(load_ir(ir_path))
            if items:
                return items, pipeline
        except Exception:
            pass

    step3_key = sd.get("step3_final_file") or sd.get("step3_revision_file") or sd.get("step2_output_file")
    if not step3_key:
        raise ValueError("未找到 step3 对齐输出或 step2 萃取输出")

    step3_path = safe_workspace_path(WORKSPACE, step3_key, must_exist=True)
    if not step3_path:
        raise ValueError(f"知识稿文件不存在: {step3_key}")

    items = []
    with _safe_workbook(str(step3_path)) as wb:
        for ws in wb.worksheets:
            headers = [str(c.value or "") for c in next(ws.iter_rows(min_row=1, max_row=1))]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if any(v for v in row):
                    items.append({headers[i]: str(row[i] or "") for i in range(min(len(headers), len(row)))})

    if not items:
        raise ValueError("知识稿中无有效数据行")
    return items, pipeline


@app.route("/api/step4/generate-cot", methods=["POST"])
def api_step4_generate_cot():
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("model", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    try:
        items, pipeline = _read_step3_knowledge_items(pipeline_id)
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)})

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        model_cfg = load_llm_config()[0] if load_llm_config() else None
    if not model_cfg:
        return jsonify({"status": "error", "error": "无可用 LLM 模型"})

    items_json = json.dumps(items[:12], ensure_ascii=False, indent=2)
    prompt = f"""你是一位银行信贷专家。请根据以下知识条目，生成一份「思维链」(Chain-of-Thought) 决策指南。

## 知识条目
{items_json}

## 要求
1. 按「环节」分组组织思维链步骤
2. 每步包含：输入条件 → 推理过程 → 输出决策
3. 引用具体的判断逻辑和反模式
4. 输出格式为 Markdown，以 "## 思维链：{{场景名}}" 开头
5. 使用中文

仅输出 Markdown 内容，不要任何额外说明。"""

    try:
        result = call_llm_with_retry(model_cfg, [{"role": "user", "content": prompt}], max_tokens=4096, temperature=0.5)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
    except Exception as e:
        return jsonify({"status": "error", "error": f"LLM 调用失败: {str(e)}"})

    slug = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "_", pipeline.get("scenario", "") or pipeline.get("name", ""))[:20]
    filename = f"COT_{slug}_{pipeline_id[:6]}.md"
    cot_path = workspace_path_for(WORKSPACE, pipeline_id, "step4", filename)
    cot_path.parent.mkdir(parents=True, exist_ok=True)
    cot_path.write_text(raw, encoding="utf-8")

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                p.setdefault("step_data", {})["step4_cot_file"] = filename
                p.setdefault("step_data", {})["step4_cot_url"] = f"/downloads/{filename}"
                p.setdefault("step_status", {})
                p["step_status"]["4"] = "done"
                p["current_step"] = max(p.get("current_step", 1), 4)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    return jsonify({
        "status": "ok",
        "filename": filename,
        "download_url": f"/downloads/{filename}",
        "preview": raw[:2000],
    })


@app.route("/api/step4/generate-qa", methods=["POST"])
def api_step4_generate_qa():
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("model", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    try:
        items, pipeline = _read_step3_knowledge_items(pipeline_id)
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)})

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        model_cfg = load_llm_config()[0] if load_llm_config() else None
    if not model_cfg:
        return jsonify({"status": "error", "error": "无可用 LLM 模型"})

    items_json = json.dumps(items[:12], ensure_ascii=False, indent=2)
    prompt = f"""你是一位银行信贷培训专家。请根据以下知识条目，生成一组「QA 对」(Question & Answer pairs)，用于 RAG 检索和客服 Agent 的 few-shot 示例。

## 知识条目
{items_json}

## 要求
1. 每条知识生成 1~2 个问答对
2. 问题模拟一线信贷员的真实提问场景
3. 答案引用知识条目中的判断逻辑和具体方法，答法要具体可操作
4. 输出格式为 JSON 数组：
   [{{"q": "问题", "a": "答案", "category": "环节名"}}]
5. 最少 6 条，最多 20 条

仅输出 JSON 数组，不要 Markdown 代码块，不要任何额外说明。"""

    try:
        result = call_llm_with_retry(model_cfg, [{"role": "user", "content": prompt}], max_tokens=4096, temperature=0.7)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
    except Exception as e:
        return jsonify({"status": "error", "error": f"LLM 调用失败: {str(e)}"})

    raw = _extract_json_from_text(raw)
    try:
        qa_pairs = json.loads(raw)
    except json.JSONDecodeError:
        qa_pairs = [{"q": "LLM 输出解析失败", "a": raw[:500]}]

    slug = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "_", pipeline.get("scenario", "") or pipeline.get("name", ""))[:20]

    # Save JSON
    json_filename = f"QA_{slug}_{pipeline_id[:6]}.json"
    qa_json_path = workspace_path_for(WORKSPACE, pipeline_id, "step4", json_filename)
    qa_json_path.parent.mkdir(parents=True, exist_ok=True)
    qa_json_path.write_text(json.dumps(qa_pairs, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save Markdown version
    md_lines = [f"# QA 对 · {pipeline.get('scenario', '') or pipeline.get('name', '')}\n"]
    for pair in qa_pairs[:30]:
        md_lines.append(f"## Q: {pair.get('q', '')}\n\n**A:** {pair.get('a', '')}\n\n---\n")
    md_filename = f"QA_{slug}_{pipeline_id[:6]}.md"
    qa_md_path = workspace_path_for(WORKSPACE, pipeline_id, "step4", md_filename)
    qa_md_path.parent.mkdir(parents=True, exist_ok=True)
    qa_md_path.write_text("".join(md_lines), encoding="utf-8")

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                p.setdefault("step_data", {})["step4_qa_file"] = json_filename
                p.setdefault("step_data", {})["step4_qa_url"] = f"/downloads/{json_filename}"
                p.setdefault("step_data", {})["step4_qa_md_file"] = md_filename
                p.setdefault("step_data", {})["step4_qa_md_url"] = f"/downloads/{md_filename}"
                p.setdefault("step_status", {})
                p["step_status"]["4"] = "done"
                p["current_step"] = max(p.get("current_step", 1), 4)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    return jsonify({
        "status": "ok",
        "qa_count": len(qa_pairs),
        "json_filename": json_filename,
        "md_filename": md_filename,
        "download_url": f"/downloads/{json_filename}",
        "md_download_url": f"/downloads/{md_filename}",
        "preview": "".join(md_lines[:20])[:2000],
    })


@app.route("/api/step4/quality", methods=["POST"])
def api_step4_quality():
    """Generate quality report — auto-reads Step4 output if pipeline_id provided."""
    pipeline_id = request.form.get("pipeline_id", "")
    excel_file = request.files.get("excel")

    input_path = None
    ir_path = None
    if pipeline_id and not excel_file:
        with _pipelines_lock:
            pipelines = load_pipelines()
            pipeline = None
            for p in pipelines:
                if p["id"] == pipeline_id:
                    pipeline = dict(p)
                    pipeline["step_data"] = dict(p.get("step_data", {}))
                    break
        if pipeline:
            step_data = pipeline.get("step_data", {})
            # 首选 Skill IR，Excel 为过渡期回退
            ir_path, _ir_key = resolve_knowledge_ir_path(WORKSPACE, step_data)
            if not ir_path:
                resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, step_data, purpose="compile")
                if resolved:
                    input_path = str(resolved)

    # IR 路径：进程内规则评分（无子进程）
    if ir_path:
        try:
            from quality_report import quality_report_from_records
            from skill_ir import ir_to_records, load_ir

            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            q = quality_report_from_records(ir_to_records(load_ir(ir_path)), config)
            if q.get("status") != "ok":
                return jsonify(q)
            report_name = f"quality_report_{uuid.uuid4().hex[:8]}.md"
            report_path = workspace_path_for(WORKSPACE, pipeline_id, "step4", report_name)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(q.get("report_markdown", ""), encoding="utf-8")
            q.pop("report_markdown", None)
            q["download_url"] = "/downloads/" + report_name
            q["input_kind"] = "ir"
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        p.setdefault("step_data", {})["step4_quality_file"] = report_name
                        p.setdefault("step_data", {})["step4_quality_url"] = "/downloads/" + report_name
                        save_pipelines(pipelines)
                        break
            return jsonify(q)
        except Exception as e:
            return jsonify({"status": "error", "error": f"质量评分失败: {str(e)}"})

    if not input_path:
        if excel_file:
            input_path = save_upload(excel_file, prefix="quality")
        else:
            return jsonify({
                "status": "error",
                "error": "未找到可分析的知识稿。请先完成「知识对齐」生成对齐稿（或上传确认版 Excel）",
            })

    report_name = f"quality_report_{uuid.uuid4().hex[:8]}.md"
    report_path_obj = workspace_path_for(WORKSPACE, pipeline_id, "step4", report_name)
    report_path_obj.parent.mkdir(parents=True, exist_ok=True)
    report_path = str(report_path_obj)

    args = ["--input", input_path, "--output", report_path]
    if SCHEMA_PATH.exists():
        args.extend(["--config", str(SCHEMA_PATH)])

    result = run_script("quality_report.py", args)

    if os.path.exists(report_path):
        result["download_url"] = "/downloads/" + report_name
        # Save to pipeline step_data
        if pipeline_id:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        p.setdefault("step_data", {})["step4_quality_file"] = report_name
                        p.setdefault("step_data", {})["step4_quality_url"] = "/downloads/" + report_name
                        save_pipelines(pipelines)
                        break

    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════
# LLM API Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/llm/models", methods=["GET"])
def api_llm_list_models():
    """List all available models (presets + custom); API keys are masked."""
    models = load_llm_config()
    result = [_sanitize_model_for_client(m) for m in models]
    return jsonify({"status": "ok", "models": result})


def _parse_model_payload(data, existing=None, require_api_key=True):
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


@app.route("/api/llm/models", methods=["POST"])
def api_llm_add_model():
    """Add a custom model."""
    data = request.get_json(force=True)
    parsed, err = _parse_model_payload(data, require_api_key=True)
    if err:
        return jsonify({"status": "error", "error": err})
    name = parsed["name"]

    with _models_lock:
        custom = []
        if CUSTOM_MODELS_PATH.exists():
            try:
                with open(str(CUSTOM_MODELS_PATH), "r", encoding="utf-8") as f:
                    custom = json.load(f)
            except (json.JSONDecodeError, IOError):
                custom = []

        existing_names = [m["name"] for m in load_llm_config()]
        if name in existing_names:
            return jsonify({"status": "error", "error": f"模型名称 '{name}' 已存在"})

        custom.append(parsed)
        save_custom_models(custom)

    return jsonify({"status": "ok", "message": f"模型 '{name}' 已添加"})


@app.route("/api/llm/models/<path:model_name>", methods=["GET"])
def api_llm_get_model(model_name):
    """Get model config for editing (API key not returned)."""
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在"})
    d = _sanitize_model_for_client(model_cfg)
    d["is_preset"] = model_cfg.get("is_preset", False)
    return jsonify({"status": "ok", "model": d})


@app.route("/api/llm/models/<path:model_name>", methods=["PUT"])
def api_llm_update_model(model_name):
    """Update a preset (saved as override) or custom model."""
    existing = get_model_by_name(model_name)
    if not existing:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在"})

    data = request.get_json(force=True)
    parsed, err = _parse_model_payload(data, existing=existing, require_api_key=False)
    if err:
        return jsonify({"status": "error", "error": err})

    new_name = parsed["name"]
    if new_name != model_name:
        return jsonify({"status": "error", "error": "暂不支持修改模型名称，请删除后重新添加"})

    save_fields = {k: v for k, v in parsed.items() if k != "name"}

    with _models_lock:
        if existing.get("is_preset"):
            overrides = load_preset_overrides()
            overrides[model_name] = save_fields
            save_preset_overrides(overrides)
        else:
            custom = []
            if CUSTOM_MODELS_PATH.exists():
                try:
                    with open(str(CUSTOM_MODELS_PATH), "r", encoding="utf-8") as f:
                        custom = json.load(f)
                except (json.JSONDecodeError, IOError):
                    custom = []
            updated = False
            for i, m in enumerate(custom):
                if m["name"] == model_name:
                    custom[i] = parsed
                    updated = True
                    break
            if not updated:
                return jsonify({"status": "error", "error": f"自定义模型 '{model_name}' 不存在"})
            save_custom_models(custom)

    return jsonify({"status": "ok", "message": f"模型 '{model_name}' 已更新"})


@app.route("/api/llm/models/<path:model_name>", methods=["DELETE"])
def api_llm_delete_model(model_name):
    """Delete a custom model (presets cannot be deleted)."""
    with _models_lock:
        custom = []
        if CUSTOM_MODELS_PATH.exists():
            try:
                with open(str(CUSTOM_MODELS_PATH), "r", encoding="utf-8") as f:
                    custom = json.load(f)
            except (json.JSONDecodeError, IOError):
                custom = []

        before = len(custom)
        custom = [m for m in custom if m["name"] != model_name]
        if len(custom) == before:
            return jsonify({"status": "error", "error": f"自定义模型 '{model_name}' 不存在或为预设模型不可删除"})

        save_custom_models(custom)

    return jsonify({"status": "ok", "message": f"模型 '{model_name}' 已删除"})


@app.route("/api/llm/test", methods=["POST"])
def api_llm_test():
    """Test connection to a model."""
    data = request.get_json(force=True)
    model_name = data.get("name", "")
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在"})

    try:
        test_cfg = dict(model_cfg)
        test_cfg["timeout"] = min(int(test_cfg.get("timeout", 300)), 20)
        result = call_llm(
            test_cfg,
            [{"role": "user", "content": "Hi"}],
            stream=False,
            max_tokens=10,
        )
        content = extract_assistant_content(result) if isinstance(result, dict) else ""
        return jsonify({"status": "ok", "message": f"连接成功，模型回复: {content[:50]}"})
    except LlmApiError as e:
        return jsonify({"status": "error", "error": str(e)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"连接失败: {str(e)}"})


@app.route("/api/llm/stream-test", methods=["POST"])
def api_llm_stream_test():
    """Stream-test LLM connection; forwards deltas as SSE to the browser."""
    data = request.get_json(force=True) or {}
    model_name = data.get("name", "")
    prompt = (data.get("prompt") or "你好，请用一句话介绍你自己。").strip()
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在"})

    messages = [{"role": "user", "content": prompt}]

    def generate():
        try:
            test_cfg = dict(model_cfg)
            test_cfg["timeout"] = min(int(test_cfg.get("timeout", 300)), 120)
            resp = call_llm(test_cfg, messages, stream=True, max_tokens=256)
            for delta in iter_llm_stream(test_cfg, resp):
                payload = json.dumps({"delta": delta}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except LlmApiError as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        except Exception as e:
            err = json.dumps({"error": f"流式连接失败: {str(e)}"}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Excel Online Editor API ──────────────────────────────────────

def _trim_excel_rows(rows, max_rows=200, max_cols=40):
    """裁剪尾部空行空列，避免 Luckysheet 渲染超大稀疏表卡顿。"""
    if not rows:
        return [[]]
    trimmed = []
    for row in rows[:max_rows]:
        trimmed.append([cell if cell is not None else "" for cell in (row or [])])
    last_r = len(trimmed) - 1
    while last_r > 0:
        if any(str(c or "").strip() for c in trimmed[last_r]):
            break
        last_r -= 1
    trimmed = trimmed[: last_r + 1]
    if not trimmed:
        return [[]]
    last_c = 0
    for row in trimmed:
        for i, c in enumerate(row):
            if str(c or "").strip():
                last_c = max(last_c, i)
    last_c = min(last_c, max_cols - 1)
    out = []
    for row in trimmed:
        r = list(row[: last_c + 1])
        while len(r) <= last_c:
            r.append("")
        out.append(r)
    return out or [[]]


@app.route("/api/excel/read", methods=["POST"])
def api_excel_read():
    """Read Excel file and return structured data for online editing."""
    input_path = None

    # Support both file upload and file_name from JSON/form
    excel_file = request.files.get("excel")
    if excel_file:
        input_path = save_upload(excel_file, prefix="edit_read")
    else:
        # Try JSON body or form data with file_name
        data = request.get_json(silent=True) or request.form.to_dict()
        file_name = data.get("file_name", "")
        if file_name:
            resolved = safe_workspace_path(WORKSPACE, file_name, must_exist=True)
            if not resolved:
                return jsonify({"status": "error", "error": f"文件不存在或路径非法: {file_name}"})
            input_path = str(resolved)

    if not input_path:
        return jsonify({"status": "error", "error": "请上传 Excel 文件或提供文件名"})

    wb = None
    try:
        wb = openpyxl.load_workbook(input_path, data_only=True)
        sheets = {}
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            raw_rows = []
            for row in ws.iter_rows(values_only=True):
                raw_rows.append([cell if cell is not None else "" for cell in row])
            rows = _trim_excel_rows(raw_rows)
            merges = []
            for merge_range in list(ws.merged_cells.ranges):
                merges.append({
                    "r": merge_range.min_row - 1,
                    "c": merge_range.min_col - 1,
                    "rs": merge_range.max_row - merge_range.min_row + 1,
                    "cs": merge_range.max_col - merge_range.min_col + 1,
                })
            sheets[sheet_name] = {"rows": rows, "merges": merges}

        # Store the file path in pipeline data for later save
        pipeline_id = request.form.get("pipeline_id", "") or (request.get_json(silent=True) or {}).get("pipeline_id", "")
        step = request.form.get("step", "3") or (request.get_json(silent=True) or {}).get("step", "3")
        if pipeline_id:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        sd = p.setdefault("step_data", {})
                        base = basename_only(input_path)
                        sd[f"step{step}_excel_path"] = base
                        if str(step) == "1" and is_step1_filename(base):
                            sd["step1_output_file"] = base
                            sd["step1_download_url"] = "/downloads/" + base
                        save_pipelines(pipelines)
                        break

        return jsonify({"status": "ok", "sheets": sheets, "file_path": basename_only(input_path)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取 Excel 失败: {str(e)}"})
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


@app.route("/api/excel/save", methods=["POST"])
def api_excel_save():
    """Save edited Excel data back to file and return download URL."""
    data = request.get_json(force=True)
    file_path = data.get("file_path", "")
    file_name = data.get("file_name", "")
    sheets = data.get("sheets", {})
    pipeline_id = data.get("pipeline_id", "")
    step = data.get("step", "3")

    resolved = resolve_client_excel_path(WORKSPACE, file_path, file_name)
    if not resolved:
        return jsonify({"status": "error", "error": "源文件不存在或路径非法，请重新打开编辑"})
    file_path = str(resolved)

    if not sheets:
        return jsonify({"status": "error", "error": "无数据可保存"})

    wb = None
    try:
        wb = openpyxl.load_workbook(file_path)

        def _sheet_payload(raw):
            if isinstance(raw, list):
                return raw, []
            if isinstance(raw, dict):
                return raw.get("rows", []), raw.get("merges", [])
            return [], []

        for sheet_name, raw in sheets.items():
            rows, merges = _sheet_payload(raw)
            if sheet_name not in wb.sheetnames:
                wb.create_sheet(sheet_name)
            ws = wb[sheet_name]

            for merge_range in list(ws.merged_cells.ranges):
                ws.unmerge_cells(str(merge_range))

            if ws.max_row:
                ws.delete_rows(1, ws.max_row)

            for r_idx, row_data in enumerate(rows, start=1):
                for c_idx, value in enumerate(row_data, start=1):
                    ws.cell(row=r_idx, column=c_idx, value=value if value != "" else None)

            for m in merges:
                rs = int(m.get("rs", 1))
                cs = int(m.get("cs", 1))
                if rs > 1 or cs > 1:
                    r0 = int(m.get("r", 0)) + 1
                    c0 = int(m.get("c", 0)) + 1
                    ws.merge_cells(
                        start_row=r0,
                        start_column=c0,
                        end_row=r0 + rs - 1,
                        end_column=c0 + cs - 1,
                    )

        # Save to a new file for download and overwrite the original
        save_name = f"edited_step{step}_{uuid.uuid4().hex[:8]}.xlsx"
        save_path_obj = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(save_name) or f"step{step}", save_name)
        save_path_obj.parent.mkdir(parents=True, exist_ok=True)
        save_path = str(save_path_obj)
        wb.save(save_path)
        wb.save(file_path)

        # Update pipeline step_data
        if pipeline_id:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        sd = p.setdefault("step_data", {})
                        base = basename_only(file_path)
                        sd[f"step{step}_excel_path"] = base
                        if str(step) == "1" and is_step1_filename(base):
                            sd["step1_output_file"] = base
                            sd["step1_download_url"] = "/downloads/" + base
                        elif str(step) == "2" and is_step2_preextract_filename(base):
                            sd["step2_output_file"] = base
                            sd["step2_download_url"] = "/downloads/" + base
                            for stale in ("step2_preview_name", "step2_preview_url", "step2_download"):
                                sd.pop(stale, None)
                        elif str(step) == "3" and is_step3_revision_filename(base):
                            sd["step3_revision_file"] = base
                            sd["step3_download_url"] = "/downloads/" + save_name
                        elif str(step) == "3" and is_step3_final_filename(base):
                            sd["step3_final_file"] = base
                            sd["step3_final_download_url"] = "/downloads/" + save_name
                        elif str(step) == "3" and is_step3_revision_filename(base):
                            sd["step3_revision_file"] = base
                            sd["step3_download_url"] = "/downloads/" + save_name
                        save_pipelines(pipelines)
                        break

        return jsonify({
            "status": "ok",
            "download_url": "/downloads/" + save_name,
            "file_path": basename_only(file_path),
            "file_name": basename_only(file_path),
            "message": "保存成功"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"保存 Excel 失败: {str(e)}"})
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


# ─── Skill Registry ───────────────────────────────────────────────
from skill_registry import SKILL_REGISTRY
@app.route("/api/skills", methods=["GET"])
def api_skills_list():
    """返回所有已注册 Skill 的简要信息"""
    skills = []
    for sid, info in SKILL_REGISTRY.items():
        skills.append({
            "id": sid,
            "name": info["name"],
            "version": info["version"],
            "description": info["description"],
            "enabled": info["enabled"],
        })
    return jsonify({"status": "ok", "skills": skills})


@app.route("/api/skills/<path:skill_id>", methods=["GET"])
def api_skill_detail(skill_id):
    """返回指定 Skill 的详细信息"""
    info = SKILL_REGISTRY.get(skill_id)
    if not info:
        return jsonify({"status": "error", "error": "Skill 不存在"}), 404
    return jsonify({"status": "ok", "skill": info})


@app.route("/api/skills/<path:skill_id>", methods=["PUT"])
def api_skill_update(skill_id):
    """更新 Skill 配置（如启用/禁用）"""
    info = SKILL_REGISTRY.get(skill_id)
    if not info:
        return jsonify({"status": "error", "error": "Skill 不存在"}), 404
    data = request.get_json(force=True)
    if "enabled" in data:
        info["enabled"] = bool(data["enabled"])
    return jsonify({"status": "ok", "skill": info})


@app.route("/api/skills/execute", methods=["POST"])
def api_skill_execute():
    """通用 Skill 执行入口，根据 skill_id 路由到对应处理器"""
    skill_id = request.form.get("skill_id", "").strip()
    if not skill_id:
        return jsonify({"status": "error", "error": "缺少 skill_id 参数"})

    info = SKILL_REGISTRY.get(skill_id)
    if not info or not info.get("enabled"):
        return jsonify({"status": "error", "error": f"Skill '{skill_id}' 不存在或未启用"})

    # Route based on skill_id
    if skill_id == "knowledge-extraction":
        return _execute_knowledge_extraction()
    elif skill_id == "knowledge-revision":
        return _execute_knowledge_revision()
    elif skill_id == "knowledge-pattern-mining":
        return _execute_pattern_mining()
    elif skill_id == "knowledge-gap-analysis":
        return _execute_gap_analysis()
    elif skill_id == "knowledge-freshness-audit":
        return _execute_freshness_audit()
    else:
        return jsonify({"status": "error", "error": f"Skill '{skill_id}' 暂无执行处理器"})


def _resolve_step1_workbook_path(pipeline_id: str):
    """从流水线 step_data 解析 Step1 场景骨架 Excel 路径。"""
    if not pipeline_id:
        return None
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                step1_file = p.get("step_data", {}).get("step1_output_file", "")
                if step1_file:
                    from pipeline_artifacts import locate_workspace_file
                    resolved = locate_workspace_file(WORKSPACE, step1_file, pipeline_id=pipeline_id)
                    if resolved:
                        return resolved
                break
    return None


def _write_step2_preextract_excel(pipeline_id: str, extracted_items: list, sub_scenarios: list | None = None):
    from step2_preextract import write_preextract_excel

    step1_path = _resolve_step1_workbook_path(pipeline_id)
    output_name = f"preextract_{uuid.uuid4().hex[:8]}.xlsx"
    output_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta = write_preextract_excel(
        step1_path=step1_path,
        output_path=output_path,
        items=extracted_items or [],
        pipeline_id=pipeline_id,
        sub_scenarios=sub_scenarios,
    )
    return output_name, meta


def _persist_step2_excel_pipeline(
    pipeline_id,
    output_name,
    extracted_text,
    style,
    count,
    *,
    md_name: str = "",
    md_url: str = "",
):
    if not pipeline_id:
        return
    if not is_step2_preextract_filename(output_name):
        raise ValueError(f"Step2 输出文件名非法（不得使用场景骨架 template_ 文件）: {output_name}")
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["skill_extract_result"] = extracted_text
                sd["skill_extract_style"] = style
                sd["step2_output_file"] = output_name
                sd["step2_download_url"] = f"/downloads/{output_name}"
                if md_name:
                    sd["step2_md_file"] = md_name
                    sd["step2_md_download_url"] = md_url or f"/downloads/{md_name}"
                else:
                    sd.pop("step2_md_file", None)
                    sd.pop("step2_md_download_url", None)
                sd["step2_extracted_count"] = count
                for stale in ("step2_preview_name", "step2_preview_url"):
                    sd.pop(stale, None)
                p.setdefault("step_status", {})
                p["step_status"]["2"] = "done"
                if p["step_status"].get("3", "pending") == "pending":
                    p["step_status"]["3"] = "active"
                p["current_step"] = max(p.get("current_step", 1), 3)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break


def _pipeline_scenario_meta(pipeline_id: str) -> dict:
    """收集 Skill IR 所需的场景元数据（Step1 表单 + 流水线属性）。"""
    if not pipeline_id:
        return {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                form = sd.get("step1_form_data", {}) or {}
                return {
                    "scenario_name": form.get("scenario_name") or p.get("scenario", "") or p.get("name", ""),
                    "scenario_content": form.get("scenario_content", ""),
                    "sub_scenarios": form.get("sub_scenarios") or [],
                    "domain": p.get("domain", ""),
                }
    return {}


def _persist_step2_skill_draft(
    pipeline_id: str,
    records: list,
    *,
    signals: dict | None = None,
    origin: str = "doc_extract",
) -> dict:
    """Step2 主产物：从萃取 records 组装 Skill IR v1 草稿并落盘 + 渲染 md 预览。

    返回 {draft_file, draft_url, draft_md_file, draft_md_url, draft_version}；失败返回 {}。
    """
    if not records:
        return {}
    try:
        from skill_ir import new_draft, render_skill_md, save_ir

        meta = _pipeline_scenario_meta(pipeline_id)
        ir = new_draft(
            meta, records,
            signals=signals or {},
            origin=origin,
            pipeline_id=pipeline_id,
        )
        draft_name = save_ir(WORKSPACE, ir, pipeline_id=pipeline_id)

        md_name, md_url = "", ""
        try:
            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            md_content = render_skill_md(ir, config)
            md_name = f"SKILL_draft_{uuid.uuid4().hex[:8]}.md"
            md_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", md_name)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_content, encoding="utf-8")
            md_url = f"/downloads/{md_name}"
        except Exception as e:
            _debug_log("E", "_persist_step2_skill_draft", "render_error", str(e)[-200:])
            md_name, md_url = "", ""

        info = {
            "draft_file": draft_name,
            "draft_url": f"/downloads/{draft_name}",
            "draft_md_file": md_name,
            "draft_md_url": md_url,
            "draft_version": 1,
        }
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p.get("id") == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step2_draft_file"] = draft_name
                    sd["step2_draft_url"] = info["draft_url"]
                    sd["step2_draft_version"] = 1
                    if md_name:
                        sd["step2_draft_md_file"] = md_name
                        sd["step2_draft_md_url"] = md_url
                    else:
                        sd.pop("step2_draft_md_file", None)
                        sd.pop("step2_draft_md_url", None)
                    save_pipelines(pipelines)
                    break
        return info
    except Exception as e:
        _debug_log("E", "_persist_step2_skill_draft", "draft_error", str(e)[-200:])
        return {}


def _step1_knowledge_columns_from_pipeline(pipeline_id: str) -> list[str]:
    if not pipeline_id:
        return []
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                cols = p.get("step_data", {}).get("step1_knowledge_columns") or []
                if isinstance(cols, list):
                    return [str(c).strip() for c in cols if str(c).strip()]
                return []
    return []


def _extract_step2_template_context(pipeline_id: str) -> dict:
    """Read Step1 template headers and produce Step2 target keys + stage chain.

    Returns:
        {
            "target_columns": ["具体方法", "知识引用", "规则引用", ...],
            "stage_chain": ["1.客户筛选", "2.客户数据匹配", "3.原因归因", "4.决策建议"],
        }
    """
    step1_path = _resolve_step1_workbook_path(pipeline_id)
    if not step1_path or not Path(step1_path).exists():
        return {
            "target_columns": _step1_knowledge_columns_from_pipeline(pipeline_id),
            "stage_chain": [],
        }

    try:
        from step1_template import detect_header_rows, find_anchor_columns

        with _safe_workbook(step1_path) as wb:
            ws = wb[wb.sheetnames[0]]
            anchor_cols = find_anchor_columns(ws)
            anchor_col_set = set(anchor_cols.values())
            header_rows = detect_header_rows(ws)

            cols = []
            seen = set()
            stage_col = None
            stage_chain = []
            for c in range(1, (ws.max_column or 1) + 1):
                if c in anchor_col_set:
                    continue
                h1 = str(ws.cell(1, c).value).strip() if ws.cell(1, c).value else ""
                h2 = str(ws.cell(2, c).value).strip() if header_rows >= 2 and ws.cell(2, c).value else ""
                if h1 and h2 and h1 != h2:
                    key = f"{h1}-{h2}"
                else:
                    key = h2 or h1
                if not key:
                    continue
                # 识别「步骤」列，用于提取因果链阶段
                if any(m in key for m in ("步骤", "环节", "stage", "phase")):
                    stage_col = c
                if key not in seen:
                    seen.add(key)
                    cols.append(key)

            # 提取阶段链：去重、保留顺序
            if stage_col:
                seen_stages = set()
                for r in range(header_rows + 1, (ws.max_row or header_rows) + 1):
                    v = ws.cell(r, stage_col).value
                    if not v:
                        continue
                    stage = str(v).strip()
                    if stage and stage not in seen_stages:
                        seen_stages.add(stage)
                        stage_chain.append(stage)

        if len(cols) < 3:
            fallback = _step1_knowledge_columns_from_pipeline(pipeline_id)
            if len(fallback) > len(cols):
                return {"target_columns": fallback, "stage_chain": stage_chain}
        return {"target_columns": cols, "stage_chain": stage_chain}
    except Exception:
        return {
            "target_columns": _step1_knowledge_columns_from_pipeline(pipeline_id),
            "stage_chain": [],
        }


def _extract_step2_target_columns(pipeline_id: str) -> list[str]:
    """兼容旧接口：只返回 target_columns。"""
    return _extract_step2_template_context(pipeline_id).get("target_columns", [])


def _normalize_extract_style(style: str) -> str:
    style = (style or "").strip()
    return style if style in EXTRACT_STYLE_RULES else "标准萃取"


def _pick_text(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _extract_item_content(item: dict, target_columns: list | None = None) -> str:
    # 自定义模板：优先从 Step1 解析出的后段列名取值（前四列锚定列不在此列表中）
    if target_columns:
        # 阶段/步骤/环节等是结构性字段，不能作为“内容”用于去重或置信度评估
        structural_markers = ("步骤", "阶段", "环节", "stage", "phase", "step")

        # 第一遍：跳过结构性字段，优先取内容/语义字段
        for col in target_columns:
            if any(m in col.lower() for m in structural_markers):
                continue
            v = item.get(col)
            if v is not None and str(v).strip():
                return str(v).strip()

        # 第二遍：任意非空字段兜底（仍避免纯结构字段）
        for col in target_columns:
            if any(m in col.lower() for m in structural_markers):
                continue
            suffix = col.split("-")[-1].strip() if "-" in col else ""
            if not suffix:
                continue
            for k, v in item.items():
                if v is not None and str(v).strip() and (str(k).endswith(suffix) or suffix in str(k)):
                    return str(v).strip()

        # 最后一遍：只要非空就取，保证至少有一个文本
        for col in target_columns:
            v = item.get(col)
            if v is not None and str(v).strip():
                return str(v).strip()

    text = _pick_text(
        item,
        (
            "content", "知识描述", "知识内容", "具体方法",
            "category", "知识分类", "步骤", "名称", "描述",
            "trigger_condition", "适用条件", "触发条件",
            "excerpt", "原文摘录", "知识引用",
        ),
    )
    if text:
        return text

    # Fallback for template-specific keys (e.g. "关键输出-名称"/"xxx-描述").
    for k, v in item.items():
        if v is None:
            continue
        key = str(k or "")
        if not key:
            continue
        s = str(v).strip()
        if not s:
            continue
        if any(mark in key for mark in ("名称", "描述", "内容", "步骤", "方法", "输出", "逻辑", "条件", "引用")):
            return s

    # Last-resort: first non-empty scalar string value.
    for v in item.values():
        if isinstance(v, (dict, list)):
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _extract_item_confidence_rank(item: dict) -> int:
    conf = _pick_text(item, ("confidence", "置信度")).lower()
    if "高" in conf or "high" in conf:
        return 3
    if "中" in conf or "medium" in conf or "med" in conf:
        return 2
    if "低" in conf or "low" in conf:
        return 1
    return 2


def _extract_item_richness(item: dict) -> int:
    keys = (
        "category", "知识分类", "步骤",
        "content", "知识描述", "知识内容", "具体方法",
        "trigger_condition", "适用条件", "触发条件", "访谈方向",
        "judgment_logic", "判断逻辑", "规则引用",
        "anti_pattern", "反模式", "反模式/踩坑提示", "描述",
        "source", "来源", "来源文档",
        "confidence", "置信度",
        "excerpt", "原文摘录", "知识引用",
    )
    seen_values = set()
    richness = 0
    for k in keys:
        v = item.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        if s in seen_values:
            continue
        seen_values.add(s)
        richness += 1
    return richness


def _apply_extract_style_rules(items: list, style: str, target_columns: list | None = None) -> tuple[list, dict]:
    """Deterministic post-processing so style differences are stable."""
    style = _normalize_extract_style(style)
    rule = EXTRACT_STYLE_RULES[style]
    template_mode = bool(target_columns)

    candidates = []
    seen = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            if isinstance(raw, (str, int, float, bool)):
                raw = {"content": str(raw)}
            else:
                continue
        text = _extract_item_content(raw, target_columns)
        if not text:
            continue
        key = "".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)

        conf_rank = _extract_item_confidence_rank(raw)
        richness = _extract_item_richness(raw)

        # Hard filter for concise mode: keep high-value entries only.
        # 自定义模板（仅后段列名变化）时放宽，避免列名不含「方法/描述」等导致被滤光。
        if style == "精简萃取" and not template_mode:
            if conf_rank < 2:
                continue
            if richness < 3 and len(text) < 24:
                continue
        elif style == "精简萃取" and template_mode and len(text) < 8:
            continue

        # Different deterministic ranking per style.
        if style == "深度萃取":
            score = (richness, conf_rank, len(text))
        elif style == "精简萃取":
            score = (conf_rank, richness, -len(text))
        else:
            score = (conf_rank, richness, len(text))
        candidates.append((score, raw))

    candidates.sort(key=lambda x: x[0], reverse=True)
    processed = [x[1] for x in candidates[: rule["max_items"]]]

    # If concise-mode hard filters accidentally drop everything, keep top candidates.
    fallback_applied = False
    if not processed and candidates:
        processed = [x[1] for x in candidates[: rule["max_items"]]]
        fallback_applied = True

    stats = {
        "raw_count": len(items or []),
        "candidate_count": len(candidates),
        "processed_count": len(processed),
        "fallback_applied": fallback_applied,
        "min_items": rule["min_items"],
        "max_items": rule["max_items"],
    }
    return processed, stats


def _execute_knowledge_extraction():
    """知识萃取 Skill 执行"""
    skill_id = request.form.get("skill_id", "knowledge-extraction")
    info = SKILL_REGISTRY.get(skill_id, {})
    model_name = request.form.get("model", "")
    style = _normalize_extract_style(request.form.get("style", "标准萃取"))
    style_rule = EXTRACT_STYLE_RULES[style]
    pipeline_id = request.form.get("pipeline_id", "")
    content = request.form.get("content", "")
    source_file = request.files.get("file")
    cached_file = os.path.basename(request.form.get("cached_file", "").strip())

    if not content and not source_file and not cached_file:
        return jsonify({"status": "error", "error": "请提供文档内容或上传文件"})
    _debug_log(
        "H2",
        "app_server.py:_execute_knowledge_extraction",
        "step2 extraction start",
        {"has_content": bool(content), "has_upload": bool(source_file), "has_cached_file": bool(cached_file)},
    )

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在或无可用模型"})

    # Read file content if uploaded
    doc_text = content
    if source_file and not doc_text:
        try:
            doc_text = extract_text_from_file(source_file)
        except Exception:
            return jsonify({"status": "error", "error": "文件读取失败"})
    elif cached_file and not doc_text:
        cached_path = resolve_cache_file_path(WORKSPACE, cached_file)
        if cached_path:
            try:
                doc_text = extract_text_from_path(str(cached_path))
            except Exception:
                pass

    template_ctx = _extract_step2_template_context(pipeline_id)
    target_columns = template_ctx.get("target_columns", [])
    stage_chain = template_ctx.get("stage_chain", [])
    skill_caps = info.get("capabilities", []) if isinstance(info, dict) else []
    cap_text = "；".join(skill_caps) if skill_caps else "结构化知识提取"
    max_tokens = style_rule["max_tokens"]
    if target_columns:
        max_tokens = max(max_tokens, 6144 if len(target_columns) > 10 else 5120)

    # ── 案例复盘模式：提取隐性信号 + 可执行知识 ──
    content_type = (request.form.get("content_type", "") or "").strip()
    if content_type == "case_review":
        system_prompt = (
            f"你是一位资深银行知识工程专家，正在从「案例复盘」中同时提取两类内容：\n"
            f"萃取风格：{style}\n\n"
            f"## 任务一：识别隐性信号（重点）\n"
            f"案例复盘中的隐性知识往往不是直接说出来的。请你特别注意以下四类信号：\n"
            f"1. **规则覆盖不到的地方**：专家提到了哪些标准流程中没有的检查步骤？哪些「多余的动作」？\n"
            f"2. **情感/直觉表达**：专家用了哪些不安/不对劲/怪怪的情感词汇？这些情感背后对应了什么可观测信号？\n"
            f"3. **破例逻辑**：专家在哪次决策中突破了标准规则？他用来合理化的理由是什么？是否值得固化为例外条件？\n"
            f"4. **关系依赖**：专家提到「问了某某人」吗？那个人知道什么别人不知道的东西？\n\n"
            f"## 任务二：抽取可执行知识条目\n"
            f"同时从案例中提取以下格式的结构化知识条目。\n\n"
            f"请按以下JSON格式输出（一个数组，不要Markdown代码块，不要任何前后说明文字）：\n"
            f'[{{\"隐性信号\": \"描述一个规则覆盖不到的场景或直觉信号（一句话）\", '
            f'\"信号类型\": \"反模式|破例|直觉|关系依赖\", '
            f'\"可执行知识\": \"从这个信号中可以提炼出什么可操作的知识？\", '
            f'\"触发条件\": \"什么情况下应该特别关注这个信号？\", '
            f'\"来源\": \"来自本案例复盘的哪个部分（标题/背景/判断/结果/重来/习惯）\", '
            f'\"置信度\": \"高|中|低\"}}]\n\n'
            f"要求：\n"
            f"1. 每条隐性信号必须是完整、自包含的陈述\n"
            f"2. 优先提取反模式和破例逻辑——这些是隐性知识的关键入口\n"
            f"3. 输出条数尽量 {style_rule['min_items']}~{style_rule['max_items']} 条\n"
            f"4. 可执行知识要具体——不能只写「注意风险」，要写「注意什么风险、怎么看、看哪里」"
        )
        # Override target columns for case review output
        target_columns = ["隐性信号", "信号类型", "可执行知识", "触发条件", "来源", "置信度"]
    elif target_columns:
        target_cols_json = json.dumps(target_columns, ensure_ascii=False)
        example_obj = {k: "" for k in target_columns}
        content_key = next(
            (k for k in target_columns if any(m in k for m in ("方法", "描述", "内容", "引用"))),
            target_columns[0],
        )
        example_obj[content_key] = "（示例：从文档抽取的一条可执行知识）"
        example_json = json.dumps([example_obj], ensure_ascii=False)

        stage_hint = ""
        item_count_hint = f"输出条数尽量 {style_rule['min_items']}~{style_rule['max_items']} 条。"
        if stage_chain:
            chain_text = " → ".join(stage_chain)
            allowed_stages = "、".join(stage_chain)
            stage_hint = (
                f"\n\n【阶段因果链 — 必须遵守】\n"
                f"本模板将业务过程划分为以下阶段，阶段之间存在因果关系：{chain_text}\n"
                f"1. 「步骤」字段只能且必须填写以下四个值之一：{allowed_stages}；严禁填写文档原始章节标题（如“业务概述”“办理流程”“营销话术”等）。\n"
                f"2. 上述每个阶段都可能产生多条知识条目，不要每个阶段只输出 1 条。\n"
                f"3. 每个阶段至少输出 3 条、最多 8 条知识条目。\n"
                f"4. 条目之间要体现阶段递进：前一阶段的输出是后一阶段的输入。\n"
                f"5. 「知识引用」和「规则引用」字段必须原样保留，作为 skill 取数逻辑。\n"
                f"6. 总计输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"
            )
            item_count_hint = f"按阶段输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"

        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n"
            f"Skill能力参考：{cap_text}\n\n"
            f"风格硬规则：{style_rule['prompt_hint']}\n"
            f"请按用户上传的萃取模板抽取知识。前四列（场景/场景说明/子场景/子场景说明）已由系统填写，"
            f"JSON 只需包含下列第5列及之后的字段（键名与表头完全一致）：\n"
            f"【输出格式 — 必须严格遵守】\n"
            f"1. 只输出一个 JSON 数组，不要用 Markdown 代码块，不要写任何前后说明文字。\n"
            f"2. 数组元素为对象；每个对象的键名必须与下列列表完全一致（含连字符）：{target_cols_json}\n"
            f"3. 键名与值均使用英文双引号；无信息的字段填空字符串 \"\"。\n"
            f"4. {item_count_hint}{stage_hint}\n"
            f"5. 输出示例（结构参考，请替换为真实抽取内容）：\n{example_json}"
        )
        if _pipeline_prefers_markdown(pipeline_id) or len(target_columns) >= 8:
            system_prompt += (
                "\n\n【深度萃取 — 多语义列】\n"
                "适用条件、判断逻辑、反模式/踩坑提示、知识描述、知识引用、规则引用等长文本字段须写完整"
                "（每条通常不少于一两句），勿只填占位词；尽量让每条记录在多数语义列上都有实质内容。"
            )
    else:
        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n"
            f"Skill能力参考：{cap_text}\n\n"
            f"风格硬规则：{style_rule['prompt_hint']}\n"
            f"请从以下文档中提取所有已显性化的知识条目，按以下JSON数组格式输出：\n"
            f'[{{"category": "判断规则|操作流程|反模式|审批标准|经验法则", '
            f'"content": "知识内容（一句话完整陈述）", '
            f'"trigger_condition": "触发条件", '
            f'"judgment_logic": "判断逻辑", '
            f'"anti_pattern": "常见反模式/踩坑提醒", '
            f'"source": "来源文档名", '
            f'"confidence": "高|中|低"}}]\n\n'
            f"要求：\n"
            f"1. 每条知识必须是完整的、自包含的陈述\n"
            f"2. category 只能是：判断规则、操作流程、反模式、审批标准、经验法则\n"
            f"3. 输出条数尽量满足 {style_rule['min_items']}~{style_rule['max_items']} 条\n"
            f"4. 尽量提取判断逻辑和反模式，这是隐性知识的关键入口"
        )

    extracted = ""
    parse_mode = "none"
    extracted_items = []
    extract_stats = {"raw_count": 0, "processed_count": 0, "min_items": style_rule["min_items"], "max_items": style_rule["max_items"]}
    output_name = None
    excel_meta = {}
    scenario_meta = _pipeline_scenario_meta(pipeline_id) if pipeline_id else {}
    sub_scenarios = scenario_meta.get("sub_scenarios", [])
    user_content = f"请从以下文档中提取知识条目：\n\n{doc_text}"
    if sub_scenarios:
        sub_names = [s.get("name", "") for s in sub_scenarios if s.get("name")]
        if sub_names:
            user_content += (
                "\n\n【子场景要求】\n"
                "本文档涉及以下子场景，请为每个子场景分别提取知识条目：\n" +
                "\n".join(f"- {name}" for name in sub_names) +
                "\n\n每条知识条目必须包含一个「子场景」字段，值为上述子场景名称之一。"
            )
    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ], stream=False, temperature=style_rule["temperature"], max_tokens=max_tokens)

        if isinstance(result, dict):
            extracted = extract_assistant_content(result)
        extracted_items, parse_mode = _parse_extracted_items(extracted)
        extracted_items = _normalize_extracted_items(extracted_items, target_columns)

        extracted_items, extract_stats = _apply_extract_style_rules(extracted_items, style, target_columns)

        # Never generate a misleading empty pre-extract workbook when model did return text.
        if not extracted_items and (extracted or "").strip():
            if parse_mode in {"json_list", "json_items", "object_recovery", "jsonl"}:
                err_text = (
                    "知识提取结果在风格规则过滤后为空，已阻止生成空萃取稿。"
                    "请切换到「标准萃取」重试，或检查自定义模板表头是否含可填写的知识列（非仅场景四列）。"
                )
            else:
                err_text = (
                    "知识提取结果解析失败（模型未返回可解析的 JSON 数组）。"
                    "自定义模板列较多时更易出现；请重试并优先使用「标准萃取」，或简化模板表头。"
                )
            return jsonify({
                "status": "error",
                "error": err_text,
                "style": style,
                "parse_mode": parse_mode,
                "target_column_count": len(target_columns),
                "used_template_columns": bool(target_columns),
                "extracted_preview": (extracted or "")[:2000],
                "style_rule": {
                    "raw_count": extract_stats.get("raw_count", 0),
                    "candidate_count": extract_stats.get("candidate_count", 0),
                    "processed_count": extract_stats.get("processed_count", 0),
                    "fallback_applied": extract_stats.get("fallback_applied", False),
                },
                "build": STEP2_EXCEL_BUILD,
            })

        output_name, excel_meta = _write_step2_preextract_excel(pipeline_id, extracted_items, sub_scenarios=sub_scenarios)
        step2_md_name, step2_md_url = _maybe_generate_markdown_artifact(
            pipeline_id,
            output_name,
            md_prefix="preextract",
            title=f"Step2 知识萃取 · {pipeline_id[:8]}",
        )
        _persist_step2_excel_pipeline(
            pipeline_id,
            output_name,
            extracted,
            style,
            len(extracted_items),
            md_name=step2_md_name,
            md_url=step2_md_url,
        )
        step1_source = ""
        if pipeline_id:
            with _pipelines_lock:
                for p in load_pipelines():
                    if p["id"] == pipeline_id:
                        step1_source = p.get("step_data", {}).get("step1_output_file", "")
                        break

        return jsonify({
            "status": "ok",
            "skill_name": info.get("name", skill_id),
            "skill_id": skill_id,
            "model": model_name,
            "style": style,
            "extracted": extracted,
            "extracted_count": len(extracted_items),
            "style_rule": {
                "mode": style,
                "min_items": extract_stats.get("min_items", style_rule["min_items"]),
                "max_items": extract_stats.get("max_items", style_rule["max_items"]),
                "raw_count": extract_stats.get("raw_count", 0),
                "processed_count": extract_stats.get("processed_count", len(extracted_items)),
            },
            "parse_mode": parse_mode,
            "download_name": output_name,
            "download_url": f"/downloads/{output_name}",
            "markdown_file": step2_md_name,
            "markdown_download_url": step2_md_url,
            "output_kind": "preextract",
            "step1_source_file": step1_source,
            "filled_rows": excel_meta.get("filled_rows", 0),
            "used_step1_template": excel_meta.get("used_step1_template", False),
            "build": STEP2_EXCEL_BUILD,
        })
    except LlmApiError as e:
        payload = {"status": "error", "error": str(e), "build": STEP2_EXCEL_BUILD}
        if output_name:
            payload.update({
                "download_name": output_name,
                "download_url": f"/downloads/{output_name}",
            })
        return jsonify(payload)
    except Exception as e:
        _debug_log(
            "H2",
            "app_server.py:_execute_knowledge_extraction",
            "step2 generic error",
            {"error": str(e)[:300]},
        )
        payload = {"status": "error", "error": f"萃取失败: {str(e)}", "build": STEP2_EXCEL_BUILD}
        return jsonify(payload)



def _resolve_step2_excel_path(pipeline_id: str):
    """Step3 修订底稿：仅使用 Step2 萃取 Excel，禁止回退到 Step1 场景骨架。"""
    if not pipeline_id:
        return None, ""
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] != pipeline_id:
                continue
            sd = p.get("step_data", {})
            step2_file = sd.get("step2_output_file", "")
            if not is_step2_preextract_filename(step2_file):
                return None, ""
            path = safe_workspace_path(WORKSPACE, step2_file, must_exist=True)
            if path:
                return str(path), sd.get("skill_extract_result", "")[:3000]
            break
    return None, ""


def _normalize_revision_style(style: str) -> str:
    style = (style or "").strip()
    return style if style in REVISION_STYLE_RULES else "标准修订"


_ALIGN_CHAT_ROUND_RE = re.compile(r"^第\d+轮专家意见[：:]\s*", re.MULTILINE)
_ALIGN_REVISION_CUE_RE = re.compile(
    r"(第\s*\d+\s*行|第\s*\d+\s*列|改为|修改|删除|新增|补充(?!意见)|调整|更正|修订|替换|"
    r"单元格|sheet|列[abcde]|行\s*\d+)",
    re.IGNORECASE,
)
_EXPLICIT_NO_OPINION_PHRASES = (
    "没有意见", "无意见", "无异议", "无需修订", "无需修改", "无修改", "没有修改",
    "无修订", "没有修订", "无变更", "保持不变", "专家无意见", "暂无意见",
    "无专家意见", "确认通过", "确认无误", "可以发布", "同意通过", "不需修改",
    "不需要修改", "没有异议", "无会议纪要修订", "无修订意见", "无修改意见",
    "无补充意见", "无补充",
)


def _normalize_expert_text_for_align(expert_text: str) -> str:
    """去掉对话轮次前缀与占位话术，便于判断是否有修订意图。"""
    t = (expert_text or "").strip()
    if not t:
        return ""
    t = _ALIGN_CHAT_ROUND_RE.sub("", t)
    t = re.sub(r"[（(]无补充意见[）)]", "", t)
    return t.strip()


def _text_is_explicit_no_opinion(expert_text: str) -> bool:
    t = _normalize_expert_text_for_align(expert_text)
    if not t:
        return True
    if _ALIGN_REVISION_CUE_RE.search(t):
        return False
    compact = re.sub(r"[\s,.，。、；;：:!！?？\-—_（）()]+", "", t.lower())
    if any(p in compact for p in _EXPLICIT_NO_OPINION_PHRASES):
        return True
    if compact in ("无", "没有", "同意", "通过", "ok", "none", "na", "n/a", "暂无"):
        return True
    return False


def _uploaded_expert_material_is_substantive(uploaded_text: str) -> bool:
    """会议纪要/访谈记录等上传内容达到可触发智能修订的阈值。"""
    t = (uploaded_text or "").strip()
    if len(t) < 30:
        return False
    return not _text_is_explicit_no_opinion(t)


def _should_pass_through_preextract(expert_text: str, uploaded_material_text: str = "") -> bool:
    """
    知识对齐直通预萃稿（不调用 LLM）：
    - 无专家文本且无实质上传材料；
    - 或专家明确表示无意见（如「暂无意见」）。
    """
    if _uploaded_expert_material_is_substantive(uploaded_material_text):
        return False
    return _text_is_explicit_no_opinion(expert_text)


def _alignment_llm_guard_rules() -> str:
    return """
## 重要约束
1. 仅根据「专家意见」中**明确写出**的修订要求生成条目；禁止仅依据知识稿内容自行推断、优化或补充修订。
2. 若专家明确表示无意见、无需修改、确认通过等，必须输出空数组 []。
3. 不得将知识稿中的待完善项自动转为修订建议，除非专家意见中点名要求修改。
"""


def _resolve_align_source_for_pipeline(pipeline_id: str) -> tuple[str | None, str]:
    """返回 (source_file_path, basename)。"""
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="align")
                if resolved:
                    return str(resolved), resolved.name
                break
    return None, ""


def _publish_final_from_source(
    pipeline_id: str,
    source_file_path: str,
    expert_text: str = "",
    style: str = "标准修订",
):
    """将当前对齐输入稿复制为 final_*.xlsx（无修订）。"""
    from datetime import datetime
    import shutil

    output_name = f"final_{pipeline_id[:8]}_{datetime.now().strftime('%H%M%S')}.xlsx"
    output_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file_path, str(output_path))
    # 始终生成 MD 预览（即使非 markdown 模式），确保对齐结果有预览可用
    md_name, md_url = _maybe_generate_markdown_artifact(
        pipeline_id,
        output_name,
        md_prefix="final",
        title=f"Step3 知识对齐 · {pipeline_id[:8]}",
    )
    if not md_name:
        # 非 markdown 模式也生成预览用 MD
        md_name = f"final_{pipeline_id[:8]}_{datetime.now().strftime('%H%M%S')}.md"
        md_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", md_name)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _excel_to_markdown_file(output_path, md_path, title=f"Step3 知识对齐 · {pipeline_id[:8]}")
            md_url = "/downloads/" + md_name
        except Exception:
            md_name = ""
            md_url = ""
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["step3_final_file"] = output_name
                sd["step3_final_download_url"] = "/downloads/" + output_name
                if md_name:
                    sd["step3_final_md_file"] = md_name
                    sd["step3_final_md_download_url"] = md_url
                else:
                    sd.pop("step3_final_md_file", None)
                    sd.pop("step3_final_md_download_url", None)
                sd["step3_final_notes"] = (expert_text or "")[:500]
                sd["step3_final_style"] = style
                sd["step3_final_count"] = 0
                sd.pop("_align_preview_notes", None)
                sd.pop("_align_preview_style", None)
                sd.pop("_align_source_file", None)
                sd.pop("_align_chat_history", None)
                p.setdefault("step_status", {})
                p["step_status"]["3"] = "done"
                if p["step_status"].get("4", "pending") == "pending":
                    p["step_status"]["4"] = "active"
                p["current_step"] = max(p.get("current_step", 1), 4)
                p["updated_at"] = datetime.now().isoformat()
                save_pipelines(pipelines)
                break
    # 对齐版 Skill IR（vN, status=aligned）— Step4/Step5 首选输入
    _persist_step3_aligned_ir(pipeline_id, output_name, notes=[], style=style)
    return output_name, md_name, md_url


def _persist_step3_aligned_ir(
    pipeline_id: str,
    final_output_name: str,
    *,
    notes: list | None = None,
    style: str = "",
) -> dict:
    """Step3 收口：从 final_*.xlsx 重建对齐版 Skill IR（vN, status=aligned）并落盘。

    过渡期 Excel ⇄ IR 投影：专家对齐仍在 Excel 机制上执行（修订色标/审计列），
    收口时以对齐稿为准重建 IR；IR 是 Step4/Step5 的首选输入。
    返回 {aligned_file, aligned_url, aligned_md_file, aligned_md_url, aligned_version}；失败 {}。
    """
    if not pipeline_id or not final_output_name:
        return {}
    try:
        from skill_ir import STATUS_ALIGNED, new_draft_from_workbook, render_skill_md, save_ir

        final_path = locate_workspace_file(WORKSPACE, final_output_name, pipeline_id=pipeline_id)
        if not final_path or not final_path.exists():
            return {}

        prev_version = 1
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {}) or {}
                    prev_version = int(
                        sd.get("step3_aligned_version")
                        or sd.get("step2_draft_version")
                        or 1
                    )
                    break

        meta_ctx = _pipeline_scenario_meta(pipeline_id)
        ir = new_draft_from_workbook(
            str(final_path), meta_ctx,
            origin="alignment", pipeline_id=pipeline_id,
        )
        ir["skill_meta"]["draft_version"] = prev_version + 1
        ir["skill_meta"]["parent_version"] = prev_version
        ir["skill_meta"]["status"] = STATUS_ALIGNED
        ir.setdefault("revision_log", []).append({
            "version": prev_version + 1,
            "by": "expert",
            "applied": len(notes or []),
            "source": "excel_alignment",
            "style": style,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        draft_name = save_ir(WORKSPACE, ir, pipeline_id=pipeline_id)

        md_name, md_url = "", ""
        try:
            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            md_content = render_skill_md(ir, config)
            md_name = f"SKILL_aligned_{uuid.uuid4().hex[:8]}.md"
            md_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", md_name)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_content, encoding="utf-8")
            md_url = f"/downloads/{md_name}"
        except Exception as e:
            _debug_log("E", "_persist_step3_aligned_ir", "render_error", str(e)[-200:])
            md_name, md_url = "", ""

        info = {
            "aligned_file": draft_name,
            "aligned_url": f"/downloads/{draft_name}",
            "aligned_md_file": md_name,
            "aligned_md_url": md_url,
            "aligned_version": prev_version + 1,
        }
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step3_aligned_file"] = draft_name
                    sd["step3_aligned_url"] = info["aligned_url"]
                    sd["step3_aligned_version"] = info["aligned_version"]
                    if md_name:
                        sd["step3_aligned_md_file"] = md_name
                        sd["step3_aligned_md_url"] = md_url
                    else:
                        sd.pop("step3_aligned_md_file", None)
                        sd.pop("step3_aligned_md_url", None)
                    save_pipelines(pipelines)
                    break
        return info
    except Exception as e:
        _debug_log("E", "_persist_step3_aligned_ir", "aligned_error", str(e)[-200:])
        return {}


def _push_step3_suggestions(pipeline_id: str, suggestions: list, source: str) -> int:
    """将 entry 级修订建议推入 Step3 建议池（专家裁决后才会应用到 IR）。"""
    if not pipeline_id or not suggestions:
        return 0
    cleaned = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        item = dict(s)
        item["id"] = uuid.uuid4().hex[:10]
        item["source"] = source
        item["created_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        cleaned.append(item)
    if not cleaned:
        return 0
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                pool = sd.get("step3_pending_suggestions")
                if not isinstance(pool, list):
                    pool = []
                pool.extend(cleaned)
                # 防建议轰炸：池上限 60 条，超出丢弃最旧的
                sd["step3_pending_suggestions"] = pool[-60:]
                save_pipelines(pipelines)
                break
    return len(cleaned)


@app.route("/api/step3/suggestions", methods=["GET"])
def api_step3_suggestions():
    """统一建议池：聚合验证回流 / 访谈转化等来源的 entry 级修订建议 + IR 冲突信号。"""
    pipeline_id = request.args.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    pool = []
    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                raw = sd.get("step3_pending_suggestions")
                if isinstance(raw, list):
                    pool = raw
                break

    # IR 冲突/重复信号（展示用，不直接可应用）
    flags_summary = {"conflicts": 0, "duplicates": 0}
    ir_path, ir_key = resolve_knowledge_ir_path(WORKSPACE, sd)
    aligned_version = sd.get("step3_aligned_version") or 0
    if ir_path:
        try:
            from skill_ir import load_ir
            ir = load_ir(ir_path)
            for e in ir.get("entries", []):
                fl = e.get("flags") or {}
                if fl.get("conflict_with"):
                    flags_summary["conflicts"] += 1
                if fl.get("duplicate_of"):
                    flags_summary["duplicates"] += 1
        except Exception:
            pass

    by_source = {}
    for s in pool:
        src = s.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    return jsonify({
        "status": "ok",
        "suggestions": pool,
        "total": len(pool),
        "by_source": by_source,
        "flags_summary": flags_summary,
        "has_ir": bool(ir_path),
        "ir_source": ir_key,
        "aligned_version": aligned_version,
        "aligned_md_url": sd.get("step3_aligned_md_url", ""),
    })


@app.route("/api/step3/apply_suggestions", methods=["POST"])
def api_step3_apply_suggestions():
    """专家采纳建议池中的修订 → 直接应用到当前 Skill IR，产出 v+1 对齐稿。

    这是验证回流闭环的落地路径：Step5 分歧建议 → 专家裁决 → IR v+1 → 可重新转化/验证。
    """
    data = request.get_json(force=True) or {}
    pipeline_id = data.get("pipeline_id", "")
    accepted_ids = set(str(i) for i in data.get("accepted_ids", []))
    rejected_ids = set(str(i) for i in data.get("rejected_ids", []))
    raw_edited = data.get("edited_suggestions", [])
    edited = {str(e.get("id")): e for e in raw_edited if isinstance(e, dict) and e.get("id")}

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})
    if not accepted_ids and not rejected_ids:
        return jsonify({"status": "error", "error": "请至少采纳或驳回一条建议"})

    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break
    pool = sd.get("step3_pending_suggestions")
    if not isinstance(pool, list) or not pool:
        return jsonify({"status": "error", "error": "建议池为空"})

    accepted = []
    for s in pool:
        sid = str(s.get("id"))
        if sid in accepted_ids:
            accepted.append({**s, **edited.get(sid, {})})

    new_info = {}
    applied = 0
    if accepted:
        ir_path, _key = resolve_knowledge_ir_path(WORKSPACE, sd)
        if not ir_path:
            return jsonify({"status": "error", "error": "未找到 Skill 草稿（IR），请先完成知识萃取"})
        try:
            from skill_ir import STATUS_ALIGNED, apply_revisions, load_ir, render_skill_md, save_ir

            ir = load_ir(ir_path)
            new_ir, applied = apply_revisions(ir, accepted, by="expert", new_status=STATUS_ALIGNED)
            draft_name = save_ir(WORKSPACE, new_ir, pipeline_id=pipeline_id)
            md_name, md_url = "", ""
            try:
                config = {}
                if SCHEMA_PATH.exists():
                    from excel_to_skill import load_scenario_config
                    config = load_scenario_config(str(SCHEMA_PATH))
                md_content = render_skill_md(new_ir, config)
                md_name = f"SKILL_aligned_{uuid.uuid4().hex[:8]}.md"
                md_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", md_name)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(md_content, encoding="utf-8")
                md_url = f"/downloads/{md_name}"
            except Exception:
                md_name, md_url = "", ""
            new_info = {
                "aligned_file": draft_name,
                "aligned_url": f"/downloads/{draft_name}",
                "aligned_md_file": md_name,
                "aligned_md_url": md_url,
                "aligned_version": new_ir["skill_meta"]["draft_version"],
            }
        except Exception as e:
            return jsonify({"status": "error", "error": f"应用建议失败: {str(e)}"})

    # 更新建议池 + 持久化新对齐稿
    handled = accepted_ids | rejected_ids
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                old_pool = sd.get("step3_pending_suggestions")
                if isinstance(old_pool, list):
                    sd["step3_pending_suggestions"] = [
                        s for s in old_pool if str(s.get("id")) not in handled
                    ]
                if new_info:
                    sd["step3_aligned_file"] = new_info["aligned_file"]
                    sd["step3_aligned_url"] = new_info["aligned_url"]
                    sd["step3_aligned_version"] = new_info["aligned_version"]
                    if new_info.get("aligned_md_file"):
                        sd["step3_aligned_md_file"] = new_info["aligned_md_file"]
                        sd["step3_aligned_md_url"] = new_info["aligned_md_url"]
                    p.setdefault("step_status", {})
                    p["step_status"]["3"] = "done"
                    if p["step_status"].get("4", "pending") == "pending":
                        p["step_status"]["4"] = "active"
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    return jsonify({
        "status": "ok",
        "applied_count": applied,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected_ids),
        "remaining": max(0, len(pool) - len(handled)),
        **new_info,
    })


def _align_no_opinion_success_payload(
    pipeline_id: str,
    source_file_path: str,
    expert_text: str,
    style: str,
    style_rule: dict,
    *,
    auto_publish: bool = True,
) -> dict:
    """无修订意见时返回成功；默认自动发布 final 稿，避免用户额外点击确认。"""
    payload = {
        "status": "ok",
        "notes": [],
        "total": 0,
        "no_opinion": True,
        "auto_finalized": False,
        "align_mode": "pass_through",
        "message": "专家意见为无需修订，已自动将当前稿确认为对齐稿。",
        "style": style,
        "style_rule": {
            "mode": style,
            "max_actions": style_rule.get("max_actions", 0),
            "raw_count": 0,
            "processed_count": 0,
        },
    }
    if auto_publish and source_file_path:
        output_name, md_name, md_url = _publish_final_from_source(
            pipeline_id,
            source_file_path,
            expert_text=expert_text,
            style=style,
        )
        payload["auto_finalized"] = True
        payload["revision_count"] = 0
        payload["accepted_count"] = 0
        payload["output_file"] = output_name
        payload["download_name"] = output_name
        payload["download_url"] = "/downloads/" + output_name
        payload["markdown_file"] = md_name
        payload["markdown_download_url"] = md_url or ""
        payload["message"] = "已自动将当前萃取稿确认为对齐稿（无修订），可直接下载。"
    else:
        payload["message"] = "专家意见为无需修订。可直接确认当前稿为对齐稿。"
    return payload


def _normalize_revision_action(action: str) -> str:
    a = (action or "").strip().lower()
    alias = {
        "修改": "modify",
        "delete": "delete",
        "删除": "delete",
        "新增": "add",
        "add": "add",
        "补充": "supplement",
        "supplement": "supplement",
    }
    return alias.get(a, a)


def _to_int(val, default=0) -> int:
    if isinstance(val, int):
        return val
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default

    # Excel column letters: A->1, B->2, AA->27
    if s.isalpha():
        n = 0
        for ch in s.upper():
            if "A" <= ch <= "Z":
                n = n * 26 + (ord(ch) - ord("A") + 1)
            else:
                return default
        return n or default

    # Strings like "第6列"/"col=8" -> extract first integer.
    digits = []
    sign = 1
    found = False
    for i, ch in enumerate(s):
        if ch == "-" and not found:
            sign = -1
            continue
        if ch.isdigit():
            digits.append(ch)
            found = True
        elif found:
            break
    if digits:
        try:
            return sign * int("".join(digits))
        except Exception:
            return default

    return default


def _apply_revision_style_rules(expert_notes: list, style: str) -> tuple[list, dict]:
    """Deterministic filtering to make revision styles behaviorally distinct."""
    style = _normalize_revision_style(style)
    rule = REVISION_STYLE_RULES[style]
    allowed_actions = rule["allowed_actions"]

    dedup = {}
    raw_count = 0
    for raw in expert_notes or []:
        if not isinstance(raw, dict):
            continue
        raw_count += 1

        action = _normalize_revision_action(raw.get("action", ""))
        if action not in allowed_actions:
            continue

        sheet = str(raw.get("sheet") or "").strip() or "Sheet1"
        row = _to_int(raw.get("row"), 0)
        col = _to_int(raw.get("col"), 0)
        old_value = str(raw.get("old_value") or "").strip()
        new_value = str(raw.get("new_value") or "").strip()
        note = str(raw.get("note") or "").strip()

        # Hard validity checks
        if action in {"modify", "supplement", "add"} and not new_value:
            continue
        if action == "modify" and not old_value:
            continue
        if action != "add" and row <= 0:
            continue
        # New rows must be explicitly positioned; otherwise they tend to pile up.
        if action == "add" and (row <= 0 or col <= 0):
            continue
        if style == "严格修订" and (action in {"add", "delete"}):
            continue

        normalized = {
            "sheet": sheet,
            "row": row,
            "col": col if col > 0 else 1,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "note": note,
        }

        if action == "add":
            dedup_key = (sheet, action, normalized["new_value"][:120])
        else:
            dedup_key = (sheet, row, normalized["col"], action)

        current = dedup.get(dedup_key)
        if current is None or len(normalized["note"]) >= len(current.get("note", "")):
            dedup[dedup_key] = normalized

    filtered = list(dedup.values())

    # Deterministic ranking by style
    if style == "严格修订":
        priority = {"modify": 3, "supplement": 2, "add": 0, "delete": 0}
    elif style == "宽松修订":
        priority = {"add": 4, "supplement": 3, "modify": 2, "delete": 1}
    else:
        priority = {"modify": 4, "supplement": 3, "add": 2, "delete": 1}

    filtered.sort(
        key=lambda n: (
            priority.get(n.get("action", ""), 0),
            len((n.get("note") or "")),
            len((n.get("new_value") or "")),
        ),
        reverse=True,
    )
    filtered = filtered[: rule["max_actions"]]

    stats = {
        "raw_count": raw_count,
        "processed_count": len(filtered),
        "max_actions": rule["max_actions"],
    }
    return filtered, stats


def _run_knowledge_revision(pipeline_id: str, expert_text: str, style: str, model_name: str = ""):
    """从 Step2/Step1 Excel + 专家意见生成带标注的修订稿。"""
    style = _normalize_revision_style(style)
    style_rule = REVISION_STYLE_RULES[style]
    excel_file, step2_content = _resolve_step2_excel_path(pipeline_id)
    if not excel_file or not os.path.exists(excel_file):
        return {"status": "error", "error": "未找到知识萃取文件，请先完成知识萃取（Step2）"}
    _debug_log(
        "H3",
        "app_server.py:_run_knowledge_revision",
        "step3 revision start",
        {"has_pipeline_id": bool(pipeline_id), "style": style, "expert_text_len": len(expert_text or "")},
    )

    try:
        from workbook_layout import build_revision_context, layout_prompt_rules, normalize_revision_notes

        excel_context_str, layout_map = build_revision_context(excel_file)
    except Exception as e:
        return {"status": "error", "error": f"读取Excel文件失败: {str(e)}"}

    style_desc = style_rule["prompt_hint"]

    step2_section = ""
    if step2_content:
        step2_section = f"\n## Step2知识萃取稿内容（参考）\n{step2_content}\n"

    prompt = f"""你是一个知识修订助手。你的任务是将专家修订意见解析为结构化的修订JSON。

## 当前Excel知识文件（含 excel_row 物理行号）
{excel_context_str}
{step2_section}
## 专家修订意见
{expert_text}

## 修订风格：{style_desc}

{layout_prompt_rules()}

## 输出要求
请生成一个JSON数组，每个元素是一条修订操作，格式如下：
```json
[
  {{
    "sheet": "工作表名称",
    "row": excel_row,
    "col": 列号(1-based，A列=1),
    "action": "modify|delete|add|supplement",
    "old_value": "原始内容（modify/delete时必填）",
    "new_value": "修订后内容（modify/add/supplement时必填）",
    "note": "修订说明"
  }}
]
```

注意：
1. row 必须使用预览中的 excel_row，不要修改表头行
2. col 使用 1-based 数字列号（A=1,B=2）
3. add 操作必须给出明确的 row 与 col（禁止 row=0/col=0）
4. 仅输出JSON数组，不要输出其他内容"""

    models_list = load_llm_config()
    if not model_name and models_list:
        model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return {"status": "error", "error": f"模型 '{model_name}' 不存在或无可用模型"}

    llm_text = ""
    try:
        llm_result = call_llm_with_retry(
            model_cfg,
            messages=[
                {"role": "system", "content": "你是一个知识修订助手，负责将专家修订意见解析为结构化的修订JSON。仅输出JSON数组，不要输出其他内容。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=style_rule["temperature"],
        )
        llm_text = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else ""
        llm_text = _extract_json_from_text(llm_text.strip())
        expert_notes = json.loads(llm_text)
        if not isinstance(expert_notes, list):
            expert_notes = [expert_notes]
        expert_notes, note_stats = _apply_revision_style_rules(expert_notes, style)
        expert_notes, row_stats = normalize_revision_notes(expert_notes, layout_map)
        note_stats["row_adjusted"] = row_stats.get("adjusted", 0)
        note_stats["row_skipped_header"] = row_stats.get("skipped_header", 0)
    except LlmApiError as e:
        return {"status": "error", "error": str(e)}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"LLM输出解析失败: {str(e)}", "raw_output": (llm_text or "")[:500]}
    except Exception as e:
        return {"status": "error", "error": f"LLM调用失败: {str(e)}"}

    try:
        from revision_processor import process_workbook
        from datetime import datetime

        output_name = f"revision_{pipeline_id[:8]}_{datetime.now().strftime('%H%M%S')}.xlsx"
        output_path = os.path.join(WORKSPACE, output_name)
        revision_count = process_workbook(excel_file, expert_notes, output_path, layouts=layout_map)

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step3_revision_file"] = output_name
                    sd["step3_download_url"] = f"/downloads/{output_name}"
                    sd["step3_revision_notes"] = expert_text
                    sd["step3_revision_style"] = style
                    sd["step3_revision_count"] = revision_count
                    sd["step3_excel_path"] = output_name
                    save_pipelines(pipelines)
                    break

        return {
            "status": "ok",
            "revision_count": revision_count,
            "output_file": output_name,
            "download_name": output_name,
            "download_url": f"/downloads/{output_name}",
            "expert_notes_json": expert_notes,
            "style_rule": {
                "mode": style,
                "max_actions": note_stats["max_actions"],
                "raw_count": note_stats["raw_count"],
                "processed_count": note_stats["processed_count"],
            },
        }
        
    except Exception as e:
        _debug_log(
            "H3",
            "app_server.py:_run_knowledge_revision",
            "step3 revision processing failure",
            {"error": str(e)[:300]},
        )
        return {"status": "error", "error": f"修订处理失败: {str(e)}"}


def _execute_knowledge_revision():
    """知识修订 Skill 执行：基于 Step2 萃取稿 + 专家意见生成修订稿。

    专家无意见时，直接透传 Step2 萃取稿作为对齐输出（不调用 LLM）。
    """
    skill_id = request.form.get("skill_id", "knowledge-revision")
    info = SKILL_REGISTRY.get(skill_id, {})
    pipeline_id = request.form.get("pipeline_id", "")
    expert_text = request.form.get("expert_text", "")
    expert_cached_file = os.path.basename(request.form.get("expert_cached_file", "").strip())
    style = request.form.get("style", "标准修订")
    model_name = request.form.get("model", "")

    if not info or not info.get("enabled"):
        return jsonify({"status": "error", "error": "知识修订技能未启用"})
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    # 加载上传材料（会议纪要/访谈记录等）
    uploaded_material_text = _load_align_expert_upload_text(
        uploaded_file=request.files.get("expert_file"),
        cached_file_name=expert_cached_file,
    )
    if not expert_text and expert_cached_file:
        try:
            cached_path = safe_workspace_path(WORKSPACE, expert_cached_file, must_exist=True)
            if cached_path:
                expert_text = extract_text_from_path(str(cached_path))
        except Exception:
            pass
    if not expert_text and uploaded_material_text:
        expert_text = uploaded_material_text

    # ── 无意见直通：不调用 LLM，直接透传 Step2 萃取稿 ──
    style = _normalize_revision_style(style)
    style_rule = REVISION_STYLE_RULES[style]
    if _should_pass_through_preextract(expert_text, uploaded_material_text):
        source_file_path, _ = _resolve_step2_excel_path(pipeline_id)
        if not source_file_path:
            return jsonify({"status": "error", "error": "未找到知识萃取文件，请先完成知识萃取（Step2）"})
        payload = _align_no_opinion_success_payload(
            pipeline_id, source_file_path, expert_text or "", style, style_rule
        )
        payload["skill_name"] = info.get("name", skill_id)
        payload["skill_id"] = skill_id
        return jsonify(payload)

    # ── 有实质意见：调用 LLM 生成修订稿 ──
    result = _run_knowledge_revision(pipeline_id, expert_text, style, model_name)
    if result.get("status") == "ok":
        result["skill_name"] = info.get("name", skill_id)
        result["skill_id"] = skill_id
    return jsonify(result)


# ─── 新 Skill: 跨案例模式发现 ─────────────────────────────────

def _execute_pattern_mining():
    """跨案例模式发现：对多个案例复盘进行交叉分析，发现反复出现的隐性信号。"""
    skill_id = request.form.get("skill_id", "knowledge-pattern-mining")
    info = SKILL_REGISTRY.get(skill_id, {})
    model_name = request.form.get("model", "")
    pipeline_id = request.form.get("pipeline_id", "")
    content = request.form.get("content", "")
    style = request.form.get("style", "标准模式发现")
    # 支持多文件上传
    uploaded_files = request.files.getlist("files")

    if not content and not uploaded_files:
        return jsonify({"status": "error", "error": "请提供至少两个案例复盘的文本，或上传案例文件"})

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不存在"})

    # 汇总所有案例文本
    all_cases = []
    if content:
        all_cases.append(content)
    for uf in uploaded_files:
        try:
            case_text = extract_text_from_file(uf)
            if case_text.strip():
                all_cases.append(f"=== 案例文件: {uf.filename} ===\n{case_text.strip()}")
        except Exception:
            pass

    if len(all_cases) < 2:
        return jsonify({"status": "error", "error": "跨案例分析需要至少 2 个案例，请补充更多案例复盘内容"})

    combined = "\n\n---分隔线---\n\n".join(all_cases)

    system_prompt = (
        f"你是一位资深银行风控专家，正在对多个案例复盘进行交叉分析，寻找**跨案例涌现的隐性知识模式**。\n\n"
        f"## 分析任务\n"
        f"请仔细阅读以下 {len(all_cases)} 个案例复盘，执行以下五步分析：\n\n"
        f"### 第一步：识别重复出现的预警信号\n"
        f"哪些具体的信号在多个案例中反复出现？请逐一列出，标注每个信号出现在哪几个案例中。\n"
        f"优先关注：财务指标之外的信号（水电费变化、人员变动、工商变更、关联交易、非正式信息源等）。\n\n"
        f"### 第二步：发现系统性风险盲区\n"
        f"这些案例共同揭示了一个什么样的**规则/流程层面**的盲区？\n"
        f"即：为什么多个案例中，按标准流程操作仍然没能提前发现风险？\n\n"
        f"### 第三步：提炼跨案例隐性知识\n"
        f"从这些案例中能提炼出哪些**可操作的新知识**？\n"
        f"这些知识不是来自单个案例，而是来自案例之间的共同模式。\n\n"
        f"### 第四步：信号优先级排序\n"
        f"按\"出现频率 × 损失严重度\"给所有信号排序，标注哪个信号是最早出现的（即最有预警价值的）。\n\n"
        f"### 第五步：生成行动建议\n"
        f"基于以上分析，给出三条具体的、可落地的行动建议。\n\n"
        f"## 输出格式\n"
        f"请严格按以下 JSON 输出（不要 Markdown 代码块，不要任何前后说明）：\n"
        f'{{\n'
        f'  "recurring_signals": [\n'
        f'    {{"signal": "信号描述", "cases": ["案例1标题", "案例2标题"], "frequency": 2, "earliest_indicator": true/false}}\n'
        f'  ],\n'
        f'  "systemic_blind_spots": ["盲区描述1", "盲区描述2"],\n'
        f'  "cross_case_knowledge": [\n'
        f'    {{"knowledge": "可执行知识", "source_signals": ["信号A", "信号B"], "actionable": "具体怎么做"}}\n'
        f'  ],\n'
        f'  "priority_ranking": [\n'
        f'    {{"rank": 1, "signal": "信号", "rationale": "为什么排第一"}}\n'
        f'  ],\n'
        f'  "action_recommendations": ["建议1", "建议2", "建议3"]\n'
        f'}}'
    )

    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"以下是要交叉分析的 {len(all_cases)} 个案例复盘：\n\n{combined[:14000]}"}
        ], stream=False, temperature=0.3, max_tokens=4096)

        llm_text = extract_assistant_content(result) if isinstance(result, dict) else ""
        llm_text = _extract_json_from_text(llm_text)
        analysis = json.loads(_repair_json_text(llm_text))

        # 生成可下载的 Markdown 报告
        report_name = f"pattern_mining_{uuid.uuid4().hex[:8]}.md"
        report_path = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(report_name) or "step4", report_name)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_pattern_mining_report(report_path, analysis, len(all_cases))

        # 持久化到 pipeline，供 Step3 修订上下文使用
        if pipeline_id:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        sd = p.setdefault("step_data", {})
                        sd["step2_pattern_mining_report"] = report_name
                        sd["step2_pattern_mining_url"] = f"/downloads/{report_name}"
                        sd["step2_pattern_mining_summary"] = {
                            "case_count": len(all_cases),
                            "top_signals": [
                                s.get("signal", "") for s in (analysis.get("recurring_signals") or [])[:5]
                            ],
                            "blind_spots": (analysis.get("systemic_blind_spots") or [])[:3],
                        }
                        save_pipelines(pipelines)
                        break

        return jsonify({
            "status": "ok",
            "skill_name": info.get("name", skill_id),
            "skill_id": skill_id,
            "model": model_name,
            "case_count": len(all_cases),
            "analysis": analysis,
            "report_name": report_name,
            "download_url": f"/downloads/{report_name}",
        })
    except json.JSONDecodeError as e:
        return jsonify({"status": "error", "error": f"LLM输出解析失败: {str(e)}", "raw": (llm_text or "")[:500]})
    except LlmApiError as e:
        return jsonify({"status": "error", "error": str(e)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"模式发现失败: {str(e)}"})


def _write_pattern_mining_report(path: Path, analysis: dict, case_count: int) -> None:
    lines = [
        f"# 跨案例模式发现报告",
        f"",
        f"- 分析案例数：**{case_count}**",
        f"- 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## 一、重复出现的预警信号",
        f"",
    ]
    for s in (analysis.get("recurring_signals") or []):
        cases_str = "、".join(s.get("cases", []))
        early = " ⚡最早信号" if s.get("earliest_indicator") else ""
        lines.append(f"- **{s.get('signal', '')}**（出现 {s.get('frequency', 0)} 次）{early}")
        lines.append(f"  - 涉及案例：{cases_str}")
        lines.append("")

    lines.append("## 二、系统性风险盲区")
    lines.append("")
    for b in (analysis.get("systemic_blind_spots") or []):
        lines.append(f"- {b}")
    lines.append("")

    lines.append("## 三、跨案例隐性知识")
    lines.append("")
    for k in (analysis.get("cross_case_knowledge") or []):
        lines.append(f"### {k.get('knowledge', '')}")
        lines.append(f"- 来源信号：{'、'.join(k.get('source_signals', []))}")
        lines.append(f"- 具体做法：{k.get('actionable', '')}")
        lines.append("")

    lines.append("## 四、信号优先级排序")
    lines.append("")
    for r in (analysis.get("priority_ranking") or []):
        lines.append(f"{r.get('rank', '?')}. **{r.get('signal', '')}** — {r.get('rationale', '')}")
    lines.append("")

    lines.append("## 五、行动建议")
    lines.append("")
    for i, a in enumerate((analysis.get("action_recommendations") or []), 1):
        lines.append(f"{i}. {a}")

    path.write_text("\n".join(lines), encoding="utf-8")


# ─── 新 Skill: 知识盲区检测 ─────────────────────────────────

def _execute_gap_analysis():
    """知识盲区检测：对比 Schema 定义的知识列与实际填充率，识别空白区域。"""
    skill_id = request.form.get("skill_id", "knowledge-gap-analysis")
    info = SKILL_REGISTRY.get(skill_id, {})
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("model", "")
    excel_file = request.files.get("excel")

    if not pipeline_id and not excel_file:
        return jsonify({"status": "error", "error": "请提供 pipeline_id 或上传知识 Excel 文件"})

    # 解析输入文件
    input_path = None
    schema_cols = []
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {})
                    schema_cols = sd.get("step1_knowledge_columns") or []
                    resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="compile")
                    if resolved:
                        input_path = str(resolved)
                    break
    if excel_file:
        input_path = save_upload(excel_file, prefix="gap_analysis")

    if not input_path or not os.path.exists(input_path):
        return jsonify({"status": "error", "error": "未找到知识 Excel 文件"})

    if not schema_cols and SCHEMA_PATH.exists():
        from scenario_schema import load_scenario_schema, resolve_knowledge_columns
        schema_cols = resolve_knowledge_columns(load_scenario_schema(SCHEMA_PATH))

    # 程序化统计每列填充率（不需要 LLM）
    col_stats = {}
    total_rows = 0
    try:
        with _safe_workbook(input_path) as wb:
            for ws in wb.worksheets:
                headers = [str(c.value or "") for c in next(ws.iter_rows(min_row=1, max_row=1))]
                col_indices = {h: i for i, h in enumerate(headers) if h}
                for r, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                    if not any(row):
                        continue
                    total_rows += 1
                    for col_name, ci in col_indices.items():
                        val = str(row[ci] or "").strip() if ci < len(row or ()) else ""
                        stat = col_stats.setdefault(col_name, {"filled": 0, "total": 0, "samples": []})
                        stat["total"] += 1
                        if len(val) >= 4:
                            stat["filled"] += 1
                            if len(stat["samples"]) < 3:
                                stat["samples"].append(val[:80])
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取 Excel 失败: {str(e)}"})

    # 生成盲区清单
    gaps = []
    for col, st in col_stats.items():
        rate = st["filled"] / max(st["total"], 1)
        if rate < 0.5:
            gaps.append({
                "column": col,
                "fill_rate": round(rate * 100, 1),
                "filled": st["filled"],
                "total": st["total"],
                "severity": "high" if rate < 0.2 else "medium",
            })

    gaps.sort(key=lambda g: g["fill_rate"])

    # 用 LLM 生成盲区解读和建议
    narrative = ""
    if gaps and model_name:
        model_cfg = get_model_by_name(model_name)
        if not model_cfg:
            models_list = load_llm_config()
            model_cfg = models_list[0] if models_list else None
        if model_cfg:
            gap_summary = "\n".join(
                f"- {g['column']}: 填充率 {g['fill_rate']}%（{g['filled']}/{g['total']}）" for g in gaps[:10]
            )
            schema_summary = "、".join(schema_cols) if schema_cols else "未获取到Schema列定义"
            try:
                llm_result = call_llm_with_retry(model_cfg, [
                    {"role": "system", "content": "你是一位知识工程专家，正在分析知识库的盲区。请用简洁的语言给出3-5条可操作的补全建议。"},
                    {"role": "user", "content": (
                        f"知识库schema定义了以下列：{schema_summary}\n\n"
                        f"以下是填充率低于50%的列（即知识盲区）：\n{gap_summary}\n"
                        f"请给出3-5条具体的补全建议，每条建议说明：（1）应该补充什么类型的知识？"
                        f"（2）建议找谁（什么背景的专家）来补充？（3）为什么这些盲区是高风险的？"
                    )}
                ], stream=False, temperature=0.3, max_tokens=1024)
                narrative = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else ""
            except Exception:
                narrative = "（LLM 解读生成失败，请手动查看盲区统计）"

    # 生成 Markdown 报告
    report_name = f"gap_analysis_{uuid.uuid4().hex[:8]}.md"
    report_path = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(report_name) or "step4", report_name)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 知识盲区检测报告",
        f"",
        f"- 总条目数：**{total_rows}**",
        f"- 检测列数：**{len(col_stats)}**",
        f"- 盲区列数（填充率<50%）：**{len(gaps)}**",
        f"- 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## 一、各列填充率",
        f"",
        f"| 列名 | 填充率 | 已填充 | 总计 |",
        f"|------|--------|--------|------|",
    ]
    for col, st in sorted(col_stats.items(), key=lambda x: x[1]["filled"] / max(x[1]["total"], 1)):
        rate = st["filled"] / max(st["total"], 1) * 100
        lines.append(f"| {col} | {rate:.0f}% | {st['filled']} | {st['total']} |")
    lines.append("")

    if gaps:
        lines.append("## 二、盲区清单（按严重度排序）")
        lines.append("")
        for g in gaps:
            sev = "🔴 高危" if g["severity"] == "high" else "🟡 中危"
            lines.append(f"- {sev} **{g['column']}**：填充率 {g['fill_rate']}%（{g['filled']}/{g['total']}）")
        lines.append("")

    if narrative:
        lines.append("## 三、补全建议")
        lines.append("")
        lines.append(narrative)

    report_path.write_text("\n".join(lines), encoding="utf-8")

    # 持久化到 pipeline，供 Step3 修订上下文使用
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step2_gap_analysis_report"] = report_name
                    sd["step2_gap_analysis_url"] = f"/downloads/{report_name}"
                    sd["step2_gap_analysis_summary"] = {
                        "total_rows": total_rows,
                        "gaps": [{"column": g["column"], "fill_rate": g["fill_rate"], "severity": g["severity"]} for g in gaps[:5]],
                    }
                    save_pipelines(pipelines)
                    break

    return jsonify({
        "status": "ok",
        "skill_name": info.get("name", skill_id),
        "skill_id": skill_id,
        "total_rows": total_rows,
        "columns_analyzed": len(col_stats),
        "gaps_found": len(gaps),
        "gaps": gaps,
        "column_stats": {k: {"fill_rate": round(v["filled"] / max(v["total"], 1) * 100, 1)} for k, v in col_stats.items()},
        "narrative": narrative,
        "report_name": report_name,
        "download_url": f"/downloads/{report_name}",
    })


# ─── 新 Skill: 知识保鲜度审计 ─────────────────────────────────

def _execute_freshness_audit():
    """知识保鲜度审计：基于 golden 知识库，检测过时规则、完整性缺口和案例突破信号。"""
    import sqlite3

    skill_id = request.form.get("skill_id", "knowledge-freshness-audit")
    info = SKILL_REGISTRY.get(skill_id, {})
    model_name = request.form.get("model", "")
    pipeline_id = request.form.get("pipeline_id", "")

    golden_path = Path(__file__).resolve().parent.parent / "data" / "golden" / "golden_test.db"
    if not golden_path.exists():
        return jsonify({"status": "error", "error": "golden 知识库不存在"})

    db = sqlite3.connect(str(golden_path))
    db.row_factory = sqlite3.Row

    rows = db.execute("""
        SELECT gi.*, gd.filename AS doc_filename, gd.source_type AS doc_source_type
        FROM golden_items gi
        LEFT JOIN golden_documents gd ON gi.document_id = gd.id
        ORDER BY gi.知识编号
    """).fetchall()

    if not rows:
        db.close()
        return jsonify({"status": "error", "error": "golden 知识库中无有效条目"})

    records = [dict(r) for r in rows]
    db.close()

    total = len(records)
    high_conf = sum(1 for r in records if str(r.get("置信度", "")).strip() == "高")
    mid_conf = sum(1 for r in records if str(r.get("置信度", "")).strip() == "中")
    low_conf = sum(1 for r in records if str(r.get("置信度", "")).strip() == "低")

    has_evidence = sum(1 for r in records if (r.get("证据数") or 0) > 0)
    has_breakthrough = sum(1 for r in records if (r.get("突破数") or 0) > 0)
    has_boundary = sum(1 for r in records if str(r.get("适用边界", "")).strip())
    has_exception = sum(1 for r in records if str(r.get("例外情形", "")).strip())
    has_logic = sum(1 for r in records if str(r.get("判断逻辑", "")).strip())
    has_antipattern = sum(1 for r in records if str(r.get("反模式踩坑提示", "")).strip())
    has_experience = sum(1 for r in records if str(r.get("经验判断", "")).strip())

    case_sources = sum(1 for r in records if r.get("doc_source_type") == "案例")
    doc_sources = sum(1 for r in records if r.get("doc_source_type") == "制度")
    meeting_sources = sum(1 for r in records if r.get("doc_source_type") == "纪要")

    stale_indicators = []
    if has_breakthrough > 0:
        stale_indicators.append(f"{has_breakthrough}/{total} 条目被案例突破（突破数>0）——相关规则需复核有效性")
    if total - has_boundary > 20:
        stale_indicators.append(f"{total - has_boundary}/{total} 条目缺少适用边界——知识适用范围不明确")
    if total - has_exception > 20:
        stale_indicators.append(f"{total - has_exception}/{total} 条目缺少例外情形——缺少决策盲区覆盖")
    if total - has_logic > 10:
        stale_indicators.append(f"{total - has_logic}/{total} 条目缺少判断逻辑——无法结构化执行")
    if high_conf / total < 0.5:
        stale_indicators.append(f"高置信度条目仅占 {round(high_conf/total*100)}%——大量知识缺乏充分验证")
    if has_evidence / total < 0.3:
        stale_indicators.append(f"仅 {round(has_evidence/total*100)}% 条目有实证支撑——知识可信度存疑")
    if case_sources > 0 and doc_sources / total > 0.5:
        stale_indicators.append(
            f"制度文档来源占比 {round(doc_sources/total*100)}%，案例复盘占比 {round(case_sources/total*100)}%"
            "——理论与实战可能存在 gap，建议增加案例复盘知识覆盖"
        )

    narrative = ""
    if model_name:
        model_cfg = get_model_by_name(model_name)
        if not model_cfg:
            models_list = load_llm_config()
            model_cfg = models_list[0] if models_list else None
        if model_cfg:
            item_sample = []
            for r in records[:20]:
                item_sample.append(
                    f"- [{r.get('环节', '未分类')}] [{r.get('知识类型', '')}] {r.get('知识编号', '')}: "
                    f"{str(r.get('具体方法', ''))[:100]}"
                    f"（置信度：{r.get('置信度', '未标')} 证据：{r.get('证据数', 0)} 突破：{r.get('突破数', 0)}"
                    f"{' 缺边界' if not str(r.get('适用边界', '')).strip() else ''}"
                    f"{' 缺例外' if not str(r.get('例外情形', '')).strip() else ''}"
                    f"{' 缺逻辑' if not str(r.get('判断逻辑', '')).strip() else ''}"
                    f"）"
                )
            breakthrough_items = []
            for r in records:
                if (r.get("突破数") or 0) > 0:
                    breakthrough_items.append(
                        f"- {r.get('知识编号')}: {str(r.get('具体方法', ''))[:100]} "
                        f"（来源：{r.get('doc_filename', r.get('来源文档', ''))}）"
                    )

            try:
                llm_result = call_llm_with_retry(model_cfg, [
                    {"role": "system", "content": (
                        "你是一位银行知识管理专家，正在审计 golden 知识库的保鲜度。"
                        "请从以下维度评估知识质量："
                        "（1）被案例突破标记的规则是否真的过时了？"
                        "（2）缺少适用边界/例外情形的知识会影响 Agent 决策的准确性吗？"
                        "（3）制度文档来源 vs 案例复盘来源的知识是否存在「理论-实战」gap？"
                        "（4）哪些环节（客户筛选/贷前尽调/审批决策/贷后监控等）的知识最不完整？"
                    )},
                    {"role": "user", "content": (
                        f"golden 知识库全量扫描（共{total}条）：\n"
                        + "\n".join(item_sample) + "\n\n"
                        + f"保鲜风险指标：\n" + "\n".join(f"- {s}" for s in stale_indicators) + "\n\n"
                        + ("被案例突破的条目：\n" + "\n".join(breakthrough_items) + "\n\n" if breakthrough_items else "")
                        + "请给出 3-5 条保鲜建议，标注最需要更新的环节和知识类型，"
                        + "评估 Agent Skill 直接使用此知识库的可靠性（高/中/低），并给出改进优先级排序。"
                    )}
                ], stream=False, temperature=0.3, max_tokens=1536)
                narrative = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else ""
            except Exception:
                narrative = "（LLM 深度审计生成失败，请参考统计数据）"

    report_name = f"freshness_audit_{uuid.uuid4().hex[:8]}.md"
    report_path = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(report_name) or "step4", report_name)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 知识保鲜度审计报告（golden 知识库）",
        "",
        f"## 审计数据源",
        f"- 数据源：**golden 知识库**（{golden_path}）",
        f"- 知识条目总数：**{total}**",
        f"- 来源分布：制度 {doc_sources} · 案例复盘 {case_sources} · 纪要 {meeting_sources}",
        "",
        "## 置信度分布",
        f"- 高：**{high_conf}**（{round(high_conf/total*100) if total else 0}%）",
        f"- 中：**{mid_conf}**（{round(mid_conf/total*100) if total else 0}%）",
        f"- 低：**{low_conf}**（{round(low_conf/total*100) if total else 0}%）",
        "",
        "## 完整性审计",
        f"- 有实证支撑：**{has_evidence}**/{total}（{round(has_evidence/total*100) if total else 0}%）",
        f"- 有判断逻辑：**{has_logic}**/{total}（{round(has_logic/total*100) if total else 0}%）",
        f"- 有反模式：**{has_antipattern}**/{total}（{round(has_antipattern/total*100) if total else 0}%）",
        f"- 有经验判断：**{has_experience}**/{total}（{round(has_experience/total*100) if total else 0}%）",
        f"- 有适用边界：**{has_boundary}**/{total}（{round(has_boundary/total*100) if total else 0}%）",
        f"- 有例外情形：**{has_exception}**/{total}（{round(has_exception/total*100) if total else 0}%）",
        f"- 被案例突破：**{has_breakthrough}**/{total}",
        f"- 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 保鲜风险指标",
        "",
    ]
    for s in stale_indicators:
        lines.append(f"- ⚠️ {s}")
    if not stale_indicators:
        lines.append("- ✅ 当前未检测到明显保鲜风险")

    if narrative:
        lines.append("")
        lines.append("## LLM 深度审计与保鲜建议")
        lines.append("")
        lines.append(narrative)

    lines.append("")
    lines.append("## Agent Skill 可靠性提示")
    lines.append("")
    if has_logic / total >= 0.5 and has_boundary / total >= 0.3 and has_breakthrough == 0:
        lines.append("- ✅ 知识库整体质量较高，Agent Skill 可直接部署使用")
    elif has_logic / total >= 0.3 and has_breakthrough <= 3:
        lines.append("- ⚠️ 知识库存在中等缺口，建议补充适用边界和例外情形后部署 Agent Skill")
    else:
        lines.append("- 🔴 知识库完整性较低，建议先按保鲜建议整改，再生成 Agent Skill")
    lines.append(f"- 建议：部署前确认 {total - has_logic} 条缺失判断逻辑的条目已人工补全")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    return jsonify({
        "status": "ok",
        "skill_name": info.get("name", skill_id),
        "skill_id": skill_id,
        "total_items": total,
        "high_confidence_pct": round(high_conf / total * 100, 1) if total else 0,
        "source_coverage_pct": round(has_evidence / total * 100, 1) if total else 0,
        "breakthrough_count": has_breakthrough,
        "completeness_score": round((has_logic + has_boundary + has_exception) / (total * 3) * 100, 1),
        "stale_indicators": stale_indicators,
        "narrative": narrative,
        "report_name": report_name,
        "download_url": f"/downloads/{report_name}",
    })


# ─── Step 3/4 pipeline outputs ────────────────────────────────────


@app.route("/api/step3/revision_context", methods=["GET"])
def api_step3_revision_context():
    """返回 Step3 修订上下文：模式发现 + 盲区检测的关键发现，供专家修订时参考。"""
    pipeline_id = request.args.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        sd = {}
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break

    ctx = {"status": "ok", "insights": [], "warnings": []}

    # 模式发现洞察
    pm = sd.get("step2_pattern_mining_summary")
    if pm:
        top = pm.get("top_signals") or []
        if top:
            ctx["insights"].append({
                "source": "跨案例模式发现",
                "icon": "🔬",
                "text": f"跨 {pm.get('case_count', '?')} 个案例发现 {len(top)} 个高频信号",
                "details": top,
            })
        blind = pm.get("blind_spots") or []
        if blind:
            ctx["warnings"].append({
                "source": "系统性风险盲区",
                "icon": "⚠️",
                "details": blind,
            })

    # 盲区检测洞察
    ga = sd.get("step2_gap_analysis_summary")
    if ga:
        gaps = ga.get("gaps") or []
        high_gaps = [g for g in gaps if g.get("severity") == "high"]
        if high_gaps:
            ctx["warnings"].append({
                "source": "知识盲区检测",
                "icon": "🎯",
                "text": f"发现 {len(high_gaps)} 个高危盲区列",
                "details": [f"{g['column']}（填充率 {g['fill_rate']}%）" for g in high_gaps],
            })
        ctx["insights"].append({
            "source": "知识盲区检测",
            "icon": "📊",
            "text": f"共 {ga.get('total_rows', '?')} 条知识，{len(gaps)} 列填充不足",
        })

    # 隐性注释提醒
    ta = sd.get("step3_tacit_annotations") or []
    if ta:
        ctx["insights"].append({
            "source": "隐性注释",
            "icon": "💡",
            "text": f"已有 {len(ta)} 条专家隐性注释可用于修订参考",
        })

    return jsonify(ctx)


@app.route("/api/step3/prev_output", methods=["GET"])
def api_step3_prev_output():
    """获取Step2知识萃取的输出件，供Step3知识修订使用"""
    pipeline_id = request.args.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                # Step2 outputs an Excel file with extracted knowledge
                step2_file = sd.get("step2_output_file", "")
                step2_download = sd.get("step2_download_url", "")
                step2_md_file = sd.get("step2_md_file", "")
                step2_md_download = sd.get("step2_md_download_url", "")
                if not is_step2_preextract_filename(step2_file):
                    return jsonify({
                        "status": "ok",
                        "has_output": False,
                        "hint": "未找到有效萃取 Excel（preextract_*.xlsx），请先完成知识萃取（Step2）",
                    })

                # Read the Step2 Excel for structure info and row count
                fields_info = []
                excel_file_to_read = step2_file
                file_path = safe_workspace_path(WORKSPACE, excel_file_to_read, must_exist=True)
                if file_path:
                    try:
                        with _safe_workbook(str(file_path)) as wb:
                            for ws_name in wb.sheetnames:
                                ws = wb[ws_name]
                                headers = []
                                if ws.max_row >= 1 and ws.max_column >= 1:
                                    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
                                        headers.append(str(cell.value) if cell.value else "")
                                row_count = ws.max_row - 1 if ws.max_row > 1 else 0
                                fields_info.append({"sheet": ws_name, "headers": headers, "rows": row_count})
                    except Exception:
                        pass

                # 读取融合元数据（多源融合场景）
                fusion_meta = None
                fusion_file = sd.get("step2_fusion_file", "")
                if fusion_file:
                    fp = safe_workspace_path(WORKSPACE, fusion_file, must_exist=True)
                    if fp:
                        try:
                            fusion_data = json.loads(fp.read_text(encoding="utf-8"))
                            fusion_meta = {
                                "duplicates": fusion_data.get("duplicates", []),
                                "conflicts": fusion_data.get("conflicts", []),
                                "source_stats": fusion_data.get("source_stats", {}),
                                "confidence_distribution": fusion_data.get("confidence_distribution", {}),
                            }
                        except Exception:
                            pass

                return jsonify({
                    "status": "ok", "has_output": True,
                    "file_name": step2_file,
                    "download_url": step2_download or ("/downloads/" + step2_file),
                    "markdown_file": step2_md_file,
                    "markdown_download_url": step2_md_download or (f"/downloads/{step2_md_file}" if step2_md_file else ""),
                    "fields_info": fields_info,
                    "scenario": sd.get("skill_extract_scenario", ""),
                    "style": sd.get("skill_extract_style", ""),
                    "extracted_count": sd.get("step2_extracted_count", 0),
                    "step1_file": sd.get("step1_output_file", ""),
                    "fusion_meta": fusion_meta,
                })
    return jsonify({"status": "ok", "has_output": False})


@app.route("/api/step3/align_output", methods=["GET"])
def api_step3_align_output():
    """获取知识对齐稿（final_*.xlsx），供智能转化等下游使用"""
    pipeline_id = request.args.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                file_path_obj, source_key = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="compile")
                if not file_path_obj:
                    return jsonify({"status": "ok", "has_output": False})
                file_path = str(file_path_obj)
                out_name = file_path_obj.name

                try:
                    fields_info = []
                    with _safe_workbook(file_path) as wb:
                        for ws_name in wb.sheetnames:
                            ws = wb[ws_name]
                            headers = []
                            if ws.max_row >= 1 and ws.max_column >= 1:
                                for cell in next(ws.iter_rows(min_row=1, max_row=1)):
                                    headers.append(str(cell.value) if cell.value else "")
                            row_count = ws.max_row - 1 if ws.max_row > 1 else 0
                            fields_info.append({"sheet": ws_name, "headers": headers, "rows": row_count})
                    if source_key == "step3_final_file":
                        dl_url = sd.get("step3_final_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step3_final_md_file", "")
                        md_url = sd.get("step3_final_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("step3_final_style", "")
                        align_count = sd.get("step3_final_count", 0)
                    elif source_key == "step3_revision_file":
                        dl_url = sd.get("step3_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step3_md_file", "")
                        md_url = sd.get("step3_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("step3_revision_style", "")
                        align_count = sd.get("step3_revision_count", 0)
                    else:
                        dl_url = sd.get("step2_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step2_md_file", "")
                        md_url = sd.get("step2_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("skill_extract_style", "")
                        align_count = sd.get("step2_extracted_count", 0)
                    return jsonify({
                        "status": "ok", "has_output": True,
                        "file_name": out_name,
                        "download_url": dl_url,
                        "markdown_file": md_name,
                        "markdown_download_url": md_url,
                        "fields_info": fields_info,
                        "revision_style": align_style,
                        "revision_count": align_count,
                        "source": source_key,
                    })
                except Exception:
                    return jsonify({"status": "ok", "has_output": False})
    return jsonify({"status": "ok", "has_output": False})


@app.route("/api/step3/finalize", methods=["POST"])
def api_step3_finalize():
    """知识对齐：基于 Step3 修订稿（或 Step2 萃取稿）+专家意见，生成最终稿"""
    pipeline_id = request.form.get("pipeline_id", "")
    expert_text = request.form.get("expert_text", "")
    expert_cached_file = os.path.basename(request.form.get("expert_cached_file", "").strip())
    style = _normalize_revision_style(request.form.get("style", "标准修订"))
    style_rule = REVISION_STYLE_RULES[style]
    model_name = request.form.get("model", "")

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})
    _debug_log(
        "H4",
        "app_server.py:api_step3_finalize",
        "step4 finalize start",
        {"has_pipeline_id": bool(pipeline_id), "style": style, "has_expert_text": bool(expert_text)},
    )

    # 支持文件上传
    if not expert_text:
        expert_file = request.files.get("expert_file")
        if expert_file and expert_file.filename:
            expert_text = extract_text_from_file(expert_file)
    if not expert_text and expert_cached_file:
        try:
            cached_path = safe_workspace_path(WORKSPACE, expert_cached_file, must_exist=True)
            if cached_path:
                expert_text = extract_text_from_path(str(cached_path))
        except Exception:
            pass

    if not expert_text:
        expert_text = ""

    # 对齐输入：已有 final 则在其上再对齐；否则用 Step2 萃取稿（四步法不要求 revision_*.xlsx）
    with _pipelines_lock:
        pipelines = load_pipelines()
        source_file_path = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="align")
                if resolved:
                    source_file_path = str(resolved)
                break

    if not source_file_path:
        return jsonify({
            "status": "error",
            "error": "未找到可对齐的知识稿。请先完成「知识萃取」生成 preextract_*.xlsx",
        })

    uploaded_material = _load_align_expert_upload_text(
        uploaded_file=request.files.get("expert_file"),
        cached_file_name=expert_cached_file,
    )
    if not expert_text and uploaded_material:
        expert_text = uploaded_material

    if _should_pass_through_preextract(expert_text, uploaded_material):
        payload = _align_no_opinion_success_payload(
            pipeline_id, source_file_path, expert_text, style, style_rule
        )
        payload["align_mode"] = "pass_through"
        return jsonify(payload)

    try:
        from workbook_layout import build_revision_context, layout_prompt_rules, normalize_revision_notes

        excel_context_str, layout_map = build_revision_context(source_file_path)
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取待对齐稿失败: {str(e)}"})

    llm_expert_text = (expert_text or "").strip()
    if uploaded_material.strip() and uploaded_material not in llm_expert_text:
        llm_expert_text = (
            f"{llm_expert_text}\n\n## 上传材料\n{uploaded_material[:12000]}"
            if llm_expert_text
            else uploaded_material[:12000]
        )

    prompt = f"""你是一位知识管理专家，正在将「专家意见」解析为结构化修订 JSON（不是主动改写知识稿）。

## 当前知识稿（含 excel_row 物理行号，仅供定位引用）
{excel_context_str[:6500]}

## 专家意见（唯一修订依据）
{llm_expert_text}

## 修订风格: {style}
硬规则：{style_rule["prompt_hint"]}

{layout_prompt_rules()}
{_alignment_llm_guard_rules()}

## 输出要求
请严格输出 JSON 数组，每条修订包含：
sheet, row（excel_row）, col（1-based）, action, old_value, new_value, note

```json
[
  {{"sheet": "Sheet1", "row": 5, "col": 3, "action": "modify", "old_value": "原内容", "new_value": "新内容", "note": "说明"}}
]
```"""

    # 调用LLM
    try:
        model = get_model_by_name(model_name)
        if not model:
            models_list = load_llm_config()
            if models_list:
                model = models_list[0]
            else:
                return jsonify({"status": "error", "error": "无可用 LLM 模型"})

        llm_result = call_llm_with_retry(
            model,
            messages=[
                {
                    "role": "system",
                    "content": "你是知识管理专家，仅将专家意见中明确提出的修订解析为 JSON 数组。无明确修订时输出 []。禁止根据知识稿自行编造修订。仅输出 JSON 数组。",
                },
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=style_rule["temperature"],
        )
        llm_text = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else ""
        llm_text = _extract_json_from_text(llm_text)

        expert_notes = json.loads(llm_text)
        if not isinstance(expert_notes, list):
            expert_notes = [expert_notes]
        expert_notes, note_stats = _apply_revision_style_rules(expert_notes, style)
        expert_notes, row_stats = normalize_revision_notes(expert_notes, layout_map)
        note_stats["row_adjusted"] = row_stats.get("adjusted", 0)
        note_stats["row_skipped_header"] = row_stats.get("skipped_header", 0)

    except LlmApiError as e:
        return jsonify({"status": "error", "error": str(e)})
    except json.JSONDecodeError as e:
        return jsonify({"status": "error", "error": f"LLM输出解析失败: {str(e)}", "raw_output": llm_text[:500]})
    except Exception as e:
        return jsonify({"status": "error", "error": f"LLM调用失败: {str(e)}"})

    if not expert_notes and not _should_pass_through_preextract(expert_text, uploaded_material):
        return jsonify({
            "status": "ok",
            "notes": [],
            "total": 0,
            "no_opinion": False,
            "align_mode": "llm_revision",
            "message": "未从专家意见/上传材料中解析出可执行的修订条目，请补充更明确的修改说明（如行号、列、修改内容）。",
            "style": style,
            "style_rule": {
                "mode": style,
                "max_actions": note_stats["max_actions"],
                "raw_count": note_stats["raw_count"],
                "processed_count": note_stats["processed_count"],
            },
        })

    # 调用 revision_processor 生成最终稿
    try:
        from revision_processor import process_workbook
        from datetime import datetime

        output_name = f"final_{pipeline_id[:8]}_{datetime.now().strftime('%H%M%S')}.xlsx"
        output_path_obj = workspace_path_for(WORKSPACE, pipeline_id, "step3", output_name)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path = str(output_path_obj)

        revision_count = process_workbook(source_file_path, expert_notes, output_path, layouts=layout_map)
        md_name, md_url = _maybe_generate_markdown_artifact(
            pipeline_id,
            output_name,
            md_prefix="final",
            title=f"Step3 知识对齐 · {pipeline_id[:8]}",
        )

        # 保存到pipeline step_data
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    p.setdefault("step_data", {})["step3_final_file"] = output_name
                    p.setdefault("step_data", {})["step3_final_download_url"] = "/downloads/" + output_name
                    p.setdefault("step_data", {})["step3_final_notes"] = expert_text[:500]
                    p.setdefault("step_data", {})["step3_final_style"] = style
                    p.setdefault("step_data", {})["step3_final_count"] = revision_count
                    if md_name:
                        p.setdefault("step_data", {})["step3_final_md_file"] = md_name
                        p.setdefault("step_data", {})["step3_final_md_download_url"] = md_url
                    else:
                        p.setdefault("step_data", {}).pop("step3_final_md_file", None)
                        p.setdefault("step_data", {}).pop("step3_final_md_download_url", None)
                    p.setdefault("step_status", {})
                    p["step_status"]["3"] = "done"
                    if p["step_status"].get("4", "pending") == "pending":
                        p["step_status"]["4"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 4)
                    p["updated_at"] = datetime.now().isoformat()
                    save_pipelines(pipelines)
                    break

        aligned_info = _persist_step3_aligned_ir(
            pipeline_id, output_name, notes=expert_notes, style=style,
        )

        skill_info = SKILL_REGISTRY.get("knowledge-revision", {})
        return jsonify({
            "status": "ok",
            "revision_count": revision_count,
            "output_file": output_name,
            "download_name": output_name,
            "download_url": "/downloads/" + output_name,
            "markdown_file": md_name,
            "markdown_download_url": md_url,
            "aligned_file": aligned_info.get("aligned_file", ""),
            "aligned_md_url": aligned_info.get("aligned_md_url", ""),
            "aligned_version": aligned_info.get("aligned_version", 0),
            "expert_notes_json": expert_notes,
            "skill_name": skill_info.get("name", "知识对齐"),
            "skill_id": "knowledge-revision",
            "style": style,
            "style_rule": {
                "mode": style,
                "max_actions": note_stats["max_actions"],
                "raw_count": note_stats["raw_count"],
                "processed_count": note_stats["processed_count"],
            },
        })
    except Exception as e:
        _debug_log(
            "H4",
            "app_server.py:api_step3_finalize",
            "step4 failure",
            {"error": str(e)[:300]},
        )
        return jsonify({"status": "error", "error": f"最终稿生成失败: {str(e)}"})


def _load_align_expert_upload_text(
    *,
    uploaded_file=None,
    cached_file_name: str = "",
) -> str:
    text_parts = []
    if uploaded_file and getattr(uploaded_file, "filename", None):
        try:
            text_parts.append(extract_text_from_file(uploaded_file).strip())
        except Exception:
            pass
    if cached_file_name:
        try:
            from pipeline_artifacts import locate_workspace_file
            cached_path = locate_workspace_file(WORKSPACE, cached_file_name)
            if cached_path and cached_path.exists():
                text_parts.append(extract_text_from_path(str(cached_path)).strip())
        except Exception:
            pass
    return "\n\n".join(p for p in text_parts if p).strip()


def _build_align_preview_from_text(
    pipeline_id: str,
    expert_text: str,
    style: str,
    model_name: str = "",
    *,
    uploaded_material_text: str = "",
):
    """根据专家意见文本生成对齐建议并缓存，供交互式审核与对话式修订复用。"""
    style = _normalize_revision_style(style)
    style_rule = REVISION_STYLE_RULES[style]
    with _pipelines_lock:
        pipelines = load_pipelines()
        source_file_path = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="align")
                if resolved:
                    source_file_path = str(resolved)
                break

    if not source_file_path:
        return {"status": "error", "error": "未找到可对齐的知识稿。请先完成「知识萃取」"}

    if _should_pass_through_preextract(expert_text, uploaded_material_text):
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["_align_preview_notes"] = []
                    sd["_align_preview_style"] = style
                    sd["_align_source_file"] = os.path.basename(source_file_path)
                    save_pipelines(pipelines)
                    break
        payload = _align_no_opinion_success_payload(
            pipeline_id, source_file_path, expert_text, style, style_rule
        )
        payload["align_mode"] = "pass_through"
        return payload

    try:
        from workbook_layout import build_revision_context, layout_prompt_rules, normalize_revision_notes
        excel_context_str, layout_map = build_revision_context(source_file_path)
    except Exception as e:
        return {"status": "error", "error": f"读取待对齐稿失败: {str(e)}"}

    source_cells = {}
    try:
        with _safe_workbook(source_file_path) as wb:
            for ws in wb.worksheets:
                for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
                    for cell in row:
                        if cell.value is not None:
                            key = f"{ws.title}:{cell.row}:{cell.column}"
                            source_cells[key] = str(cell.value)
    except Exception:
        pass

    llm_expert_text = (expert_text or "").strip()
    if uploaded_material_text.strip():
        if llm_expert_text:
            llm_expert_text = (
                f"{llm_expert_text}\n\n## 上传材料（会议纪要/访谈记录等）\n{uploaded_material_text[:12000]}"
            )
        else:
            llm_expert_text = uploaded_material_text[:12000]

    prompt = f"""你是一位知识管理专家，正在将「专家意见」解析为结构化修订 JSON（不是主动改写知识稿）。

## 当前知识稿（含 excel_row 物理行号，仅供定位引用）
{excel_context_str[:6500]}

## 专家意见（唯一修订依据）
{llm_expert_text}

## 修订风格: {style}
硬规则：{style_rule["prompt_hint"]}

{layout_prompt_rules()}
{_alignment_llm_guard_rules()}

## 输出要求
请严格输出 JSON 数组，每条修订包含：
sheet, row（excel_row）, col（1-based）, action, old_value, new_value, note

```json
[
  {{"sheet": "Sheet1", "row": 5, "col": 3, "action": "modify", "old_value": "原内容", "new_value": "新内容", "note": "说明"}}
]
```"""

    try:
        model = get_model_by_name(model_name)
        if not model:
            models_list = load_llm_config()
            if models_list:
                model = models_list[0]
            else:
                return {"status": "error", "error": "无可用 LLM 模型"}

        llm_result = call_llm_with_retry(
            model,
            messages=[
                {
                    "role": "system",
                    "content": "你是知识管理专家，仅将专家意见中明确提出的修订解析为 JSON 数组。无明确修订时输出 []。禁止根据知识稿自行编造修订。仅输出 JSON 数组。",
                },
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=style_rule["temperature"],
        )
        llm_text = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else ""
        llm_text = _extract_json_from_text(llm_text)

        expert_notes = json.loads(llm_text)
        if not isinstance(expert_notes, list):
            expert_notes = [expert_notes]
        expert_notes, note_stats = _apply_revision_style_rules(expert_notes, style)
        expert_notes, row_stats = normalize_revision_notes(expert_notes, layout_map)
        note_stats["row_adjusted"] = row_stats.get("adjusted", 0)
        note_stats["row_skipped_header"] = row_stats.get("skipped_header", 0)
    except LlmApiError as e:
        return {"status": "error", "error": str(e)}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"LLM输出解析失败: {str(e)}", "raw_output": llm_text[:500]}
    except Exception as e:
        return {"status": "error", "error": f"LLM调用失败: {str(e)}"}

    if not expert_notes:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["_align_preview_notes"] = []
                    sd["_align_preview_style"] = style
                    sd["_align_source_file"] = os.path.basename(source_file_path)
                    save_pipelines(pipelines)
                    break
        # expert_notes 为空时，直通生成对齐稿（不再报错）
        payload = _align_no_opinion_success_payload(
            pipeline_id, source_file_path, expert_text, style, style_rule
        )
        payload["align_mode"] = "pass_through"
        payload["message"] = "未从专家意见/上传材料中解析出可执行的修订条目，已将当前稿确认为对齐稿。如需精细修订，请补充更明确的修改说明（建议注明行号、列名与修改内容）。"
        return payload

    for i, note in enumerate(expert_notes):
        note["id"] = i
        cell_key = f"{note.get('sheet', '')}:{note.get('row', '')}:{note.get('col', '')}"
        if not note.get("old_value") and cell_key in source_cells:
            note["old_value"] = source_cells[cell_key]

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["_align_preview_notes"] = expert_notes
                sd["_align_preview_style"] = style
                sd["_align_source_file"] = os.path.basename(source_file_path)
                save_pipelines(pipelines)
                break

    return {
        "status": "ok",
        "notes": expert_notes,
        "total": len(expert_notes),
        "align_mode": "llm_revision",
        "style": style,
        "style_rule": {
            "mode": style,
            "max_actions": note_stats["max_actions"],
            "raw_count": note_stats["raw_count"],
            "processed_count": note_stats["processed_count"],
        },
    }


@app.route("/api/step3/align_preview", methods=["POST"])
def api_step3_align_preview():
    """知识对齐 - 校正性：返回 AI 对齐建议列表，但不实际修改 Excel。"""
    pipeline_id = request.form.get("pipeline_id", "")
    expert_text = request.form.get("expert_text", "")
    expert_cached_file = os.path.basename(request.form.get("expert_cached_file", "").strip())
    style = _normalize_revision_style(request.form.get("style", "标准修订"))
    style_rule = REVISION_STYLE_RULES[style]
    model_name = request.form.get("model", "")

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})
    # region agent log
    _agent_debug_log(
        "run-1",
        "H1",
        "app_server.py:api_step3_align_preview:entry",
        "align_preview request received",
        {
            "has_pipeline_id": bool(pipeline_id),
            "style": style,
            "has_expert_text": bool(expert_text),
            "has_cached_file": bool(expert_cached_file),
            "model_name": model_name or "",
        },
    )
    # endregion

    if not expert_text:
        expert_file = request.files.get("expert_file")
        if expert_file and expert_file.filename:
            expert_text = extract_text_from_file(expert_file)
    if not expert_text and expert_cached_file:
        try:
            cached_path = safe_workspace_path(WORKSPACE, expert_cached_file, must_exist=True)
            if cached_path:
                expert_text = extract_text_from_path(str(cached_path))
        except Exception:
            pass

    if not expert_text:
        expert_text = ""

    uploaded_material = _load_align_expert_upload_text(
        uploaded_file=request.files.get("expert_file"),
        cached_file_name=expert_cached_file,
    )
    preview = _build_align_preview_from_text(
        pipeline_id,
        expert_text,
        style,
        model_name,
        uploaded_material_text=uploaded_material,
    )
    return jsonify(preview)


@app.route("/api/step3/align_chat", methods=["POST"])
def api_step3_align_chat():
    """知识对齐 - 校正性：对话式知识对齐，按聊天轮次累积专家意见，返回模型回复与可审核修订建议。"""
    pipeline_id = request.form.get("pipeline_id", "")
    message = (request.form.get("message", "") or request.form.get("expert_text", "")).strip()
    expert_cached_file = os.path.basename(request.form.get("expert_cached_file", "").strip())
    style = _normalize_revision_style(request.form.get("style", "标准修订"))
    model_name = request.form.get("model", "")

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    uploaded_material = _load_align_expert_upload_text(
        uploaded_file=request.files.get("expert_file"),
        cached_file_name=expert_cached_file,
    )
    if not message and uploaded_material:
        message = uploaded_material[:8000]

    user_history = []
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                history = sd.get("_align_chat_history", [])
                if isinstance(history, list):
                    user_history = [h for h in history if isinstance(h, dict)]
                break

    if message or _uploaded_expert_material_is_substantive(uploaded_material):
        user_history.append({
            "role": "user",
            "content": (message or uploaded_material[:2000]).strip(),
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 仅保留最近 12 轮，避免上下文无限增长
    user_history = user_history[-24:]
    user_turns = [h for h in user_history if h.get("role") == "user" and str(h.get("content", "")).strip()]
    check_text = "\n\n".join(str(item.get("content", "")).strip() for item in user_turns[-12:])
    merged_expert_text = "\n\n".join(
        [f"第{i + 1}轮专家意见：\n{str(item.get('content', '')).strip()}" for i, item in enumerate(user_turns[-12:])]
    )
    pass_through = _should_pass_through_preextract(check_text, uploaded_material)
    expert_for_build = check_text if pass_through else (merged_expert_text or check_text)

    preview_result = _build_align_preview_from_text(
        pipeline_id,
        expert_for_build,
        style,
        model_name,
        uploaded_material_text=uploaded_material,
    )
    if preview_result.get("status") != "ok":
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["_align_chat_history"] = user_history
                    save_pipelines(pipelines)
                    break
        return jsonify(preview_result)

    notes = preview_result.get("notes", []) or []
    if notes:
        assistant_reply = (
            f"已结合当前与历史意见，生成 {len(notes)} 条修订建议。"
            "请在下方逐条采纳/驳回/编辑后生成对齐稿。"
        )
    elif preview_result.get("auto_finalized"):
        assistant_reply = preview_result.get("message") or "已自动确认当前稿为对齐稿（无修订）。"
    else:
        assistant_reply = preview_result.get("message") or "本轮未识别到可执行修订。你可以继续补充更具体的修改点。"

    user_history.append({
        "role": "assistant",
        "content": assistant_reply,
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    user_history = user_history[-24:]

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["_align_chat_history"] = user_history
                save_pipelines(pipelines)
                break

    preview_result["assistant_reply"] = assistant_reply
    preview_result["chat_history"] = user_history
    return jsonify(preview_result)


@app.route("/api/step3/apply_notes", methods=["POST"])
def api_step3_apply_notes():
    """交互式对齐 Phase 2：按用户选择的建议子集生成 final_*.xlsx。"""
    data = request.get_json(force=True)
    pipeline_id = data.get("pipeline_id", "")
    accepted_ids = set(data.get("accepted_ids", []))
    raw_edited_notes = data.get("edited_notes", [])
    tacit_annotations = data.get("tacit_annotations", [])  # 隐性注释 — 专家修订背后的经验分享
    # region agent log
    _agent_debug_log(
        "run-1",
        "H2",
        "app_server.py:api_step3_apply_notes:entry",
        "apply_notes request received",
        {
            "has_pipeline_id": bool(pipeline_id),
            "accepted_count": len(accepted_ids),
            "accepted_id_types": sorted(list({type(v).__name__ for v in accepted_ids})),
            "edited_count_raw": len(raw_edited_notes) if isinstance(raw_edited_notes, list) else -1,
        },
    )
    # endregion
    edited_notes = {int(n["id"]): n for n in raw_edited_notes if "id" in n}

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})
    if not accepted_ids:
        return jsonify({"status": "error", "error": "请至少采纳一条对齐建议"})

    with _pipelines_lock:
        pipelines = load_pipelines()
        source_file_path = None
        cached_notes = None
        cached_style = "标准修订"
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                cached_notes = sd.get("_align_preview_notes")
                cached_style = sd.get("_align_preview_style", "标准修订")
                src_name = sd.get("_align_source_file", "")
                if src_name:
                    resolved = safe_workspace_path(WORKSPACE, src_name, must_exist=True)
                    if resolved:
                        source_file_path = str(resolved)
                if not source_file_path:
                    resolved2, _ = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="align")
                    if resolved2:
                        source_file_path = str(resolved2)
                break

    if not cached_notes:
        return jsonify({"status": "error", "error": "未找到预览建议缓存，请重新执行「生成对齐建议」"})
    if not source_file_path:
        return jsonify({"status": "error", "error": "未找到源知识稿"})

    final_notes = []
    for note in cached_notes:
        nid = note.get("id")
        if nid not in accepted_ids:
            continue
        if nid in edited_notes:
            merged = {**note, **edited_notes[nid]}
            final_notes.append(merged)
        else:
            final_notes.append(note)
    # region agent log
    _agent_debug_log(
        "run-1",
        "H3",
        "app_server.py:api_step3_apply_notes:selection",
        "apply_notes selection materialized",
        {
            "cached_notes_count": len(cached_notes),
            "accepted_ids_count": len(accepted_ids),
            "edited_notes_count": len(edited_notes),
            "final_notes_count": len(final_notes),
        },
    )
    # endregion

    try:
        from workbook_layout import build_revision_context, normalize_revision_notes
        _, layout_map = build_revision_context(source_file_path)
        from revision_processor import process_workbook
        from datetime import datetime

        output_name = f"final_{pipeline_id[:8]}_{datetime.now().strftime('%H%M%S')}.xlsx"
        output_path = os.path.join(WORKSPACE, output_name)
        revision_count = process_workbook(source_file_path, final_notes, output_path, layouts=layout_map, tacit_annotations=tacit_annotations)
        md_name, md_url = _maybe_generate_markdown_artifact(
            pipeline_id,
            output_name,
            md_prefix="final",
            title=f"Step3 知识对齐 · {pipeline_id[:8]}",
        )

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step3_final_file"] = output_name
                    sd["step3_final_download_url"] = "/downloads/" + output_name
                    sd["step3_final_notes"] = json.dumps(
                        [{"action": n.get("action"), "note": n.get("note", "")} for n in final_notes],
                        ensure_ascii=False,
                    )[:500]
                    if tacit_annotations:
                        sd["step3_tacit_annotations"] = [
                            {"note_id": a.get("note_id"), "action": a.get("action"),
                             "knowledge_id": a.get("knowledge_id", ""),
                             "category": a.get("category", "经验判断"),
                             "question": a.get("question"), "answer": a.get("answer")}
                            for a in tacit_annotations if a.get("answer")
                        ]
                    sd["step3_final_style"] = cached_style
                    sd["step3_final_count"] = revision_count
                    if md_name:
                        sd["step3_final_md_file"] = md_name
                        sd["step3_final_md_download_url"] = md_url
                    else:
                        sd.pop("step3_final_md_file", None)
                        sd.pop("step3_final_md_download_url", None)
                    sd.pop("_align_preview_notes", None)
                    sd.pop("_align_preview_style", None)
                    sd.pop("_align_source_file", None)
                    sd.pop("_align_chat_history", None)
                    p.setdefault("step_status", {})
                    p["step_status"]["3"] = "done"
                    if p["step_status"].get("4", "pending") == "pending":
                        p["step_status"]["4"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 4)
                    p["updated_at"] = datetime.now().isoformat()
                    save_pipelines(pipelines)
                    break
        # region agent log
        _agent_debug_log(
            "run-1",
            "H4",
            "app_server.py:api_step3_apply_notes:success",
            "apply_notes generated final file",
            {
                "output_name": output_name,
                "revision_count": revision_count,
                "accepted_count": len(final_notes),
            },
        )
        # endregion

        aligned_info = _persist_step3_aligned_ir(
            pipeline_id, output_name, notes=final_notes, style=cached_style,
        )

        return jsonify({
            "status": "ok",
            "revision_count": revision_count,
            "accepted_count": len(final_notes),
            "total_suggested": len(cached_notes),
            "output_file": output_name,
            "download_name": output_name,
            "download_url": "/downloads/" + output_name,
            "markdown_file": md_name,
            "markdown_download_url": md_url,
            "aligned_file": aligned_info.get("aligned_file", ""),
            "aligned_md_url": aligned_info.get("aligned_md_url", ""),
            "aligned_version": aligned_info.get("aligned_version", 0),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"生成对齐稿失败: {str(e)}"})


@app.route("/api/step3/confirm_as_is", methods=["POST"])
def api_step3_confirm_as_is():
    """专家无修订意见时，将当前对齐输入稿直接确认为 final_*.xlsx。"""
    data = request.get_json(force=True) or {}
    pipeline_id = data.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    source_file_path, _ = _resolve_align_source_for_pipeline(pipeline_id)
    if not source_file_path:
        return jsonify({"status": "error", "error": "未找到可对齐的知识稿"})

    try:
        style = "标准修订"
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    style = p.get("step_data", {}).get("_align_preview_style") or style
                    break
        output_name, md_name, md_url = _publish_final_from_source(pipeline_id, source_file_path, style=style)
        return jsonify({
            "status": "ok",
            "revision_count": 0,
            "accepted_count": 0,
            "total_suggested": 0,
            "output_file": output_name,
            "download_name": output_name,
            "download_url": "/downloads/" + output_name,
            "markdown_file": md_name,
            "markdown_download_url": md_url,
            "message": "已确认当前稿为对齐稿（无修订）",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"确认对齐稿失败: {str(e)}"})


# ─── Interview API (方案三) ──────────────────────────────────────

@app.route("/api/interview/probe", methods=["POST"])
def api_interview_probe():
    """结构化访谈追问生成：输入一条知识 + 方法 → LLM 生成追问。"""
    data = request.get_json(force=True) if request.is_json else {}
    method = data.get("method", "case_reverse")
    knowledge_item = data.get("knowledge", {})
    model_name = data.get("model", "")

    if not knowledge_item:
        return jsonify({"status": "error", "error": "请提供知识条目"})
    if method not in ("case_reverse", "contrast_probe", "limit_hypothesis"):
        return jsonify({"status": "error", "error": f"未知访谈方法: {method}"})

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型不存在: {model_name}"})

    from interview_session import build_interview_prompt, parse_interview_result
    system_prompt, user_prompt = build_interview_prompt(method, knowledge_item)

    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], stream=False, temperature=0.3, max_tokens=1024)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
        probes = parse_interview_result(raw)
        return jsonify({
            "status": "ok",
            "method": method,
            "method_name": INTERVIEW_METHODS.get(method, {}).get("name", method) if "INTERVIEW_METHODS" in dir() else method,
            "probes": probes,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"访谈追问生成失败: {str(e)}"})


# ─── Validation Replay API (方案四) ──────────────────────────────

@app.route("/api/validate/replay", methods=["POST"])
def api_validate_replay():
    """显性化校验闭环：上传历史案例，用知识库判断，与专家结论对比。"""
    model_name = request.form.get("model", "")
    pipeline_id = request.form.get("pipeline_id", "")
    cases_json = request.form.get("cases", "")
    cases_file = request.files.get("cases_file")

    # 加载案例
    cases = []
    if cases_json:
        try:
            cases = json.loads(cases_json)
        except json.JSONDecodeError:
            return jsonify({"status": "error", "error": "案例 JSON 格式错误"})
    elif cases_file:
        try:
            cases = json.load(cases_file)
        except json.JSONDecodeError:
            text = cases_file.read().decode("utf-8", errors="replace")
            try:
                cases = json.loads(text)
            except json.JSONDecodeError:
                return jsonify({"status": "error", "error": "案例文件 JSON 格式错误"})
    if not cases:
        return jsonify({"status": "error", "error": "请提供至少 1 个历史案例"})

    # 加载知识库文本
    knowledge_text = ""
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {})
                    resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="compile")
                    if resolved:
                        from excel_to_skill import read_excel_knowledge
                        records, _ = read_excel_knowledge(str(resolved))
                        from excel_to_skill import format_knowledge_item
                        knowledge_text = "\n\n".join(format_knowledge_item(r) for r in records)
                    break
    if not knowledge_text:
        return jsonify({"status": "error", "error": "未找到知识库内容，请提供 pipeline_id"})

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": "模型未配置"})

    from validation_replay import build_validation_prompt, compare_predictions, generate_replay_report
    system_prompt, user_prompt = build_validation_prompt(knowledge_text, cases)

    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], stream=False, temperature=0.1, max_tokens=4096)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
        try:
            predictions = json.loads(raw)
            if not isinstance(predictions, list):
                predictions = [{"case_id": "unknown", "prediction": raw[:200]}]
        except json.JSONDecodeError:
            predictions = [{"case_id": "unknown", "prediction": raw[:200]}]

        comparison = compare_predictions(predictions, cases)
        report = generate_replay_report(comparison, cases, predictions)

        report_name = f"validation_replay_{uuid.uuid4().hex[:8]}.md"
        report_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", report_name)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")

        return jsonify({
            "status": "ok",
            "hit_rate": comparison["hit_rate"],
            "hits": comparison["hits"],
            "total": comparison["total_cases"],
            "mismatch_count": comparison["mismatch_count"],
            "mismatches": comparison["mismatches"],
            "report_name": report_name,
            "download_url": f"/downloads/{report_name}",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"校验回放失败: {str(e)}"})


# ─── Step5 验证环节（回放 + 回流） ────────────────────────────────

def _resolve_skill_text_for_validation(pipeline_id: str) -> tuple[str, str]:
    """验证对象解析：优先 Step4 SKILL 终版文本 → IR 渲染 → Excel 知识文本。

    返回 (knowledge_text, source_kind)。
    """
    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break
    if not sd:
        return "", ""

    # 1) Step4 已发布的 SKILL 终版（验证最终交付物本身）
    skill_file = sd.get("step4_skill_file", "")
    if skill_file:
        skill_path = safe_workspace_path(WORKSPACE, skill_file, must_exist=True)
        if skill_path:
            try:
                return skill_path.read_text(encoding="utf-8"), "skill_final"
            except Exception:
                pass

    # 2) Skill IR 渲染（对齐版 → 萃取稿）
    ir_path, ir_key = resolve_knowledge_ir_path(WORKSPACE, sd)
    if ir_path:
        try:
            from skill_ir import load_ir, render_skill_md
            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            return render_skill_md(load_ir(ir_path), config), ir_key
        except Exception:
            pass

    # 3) 过渡期回退：Excel 知识文本
    resolved, _src = resolve_knowledge_workbook_path(WORKSPACE, sd, purpose="compile")
    if resolved:
        try:
            from excel_to_skill import format_knowledge_item, read_excel_knowledge
            records, _ = read_excel_knowledge(str(resolved))
            return "\n\n".join(format_knowledge_item(r) for r in records), "excel"
        except Exception:
            pass
    return "", ""


def _load_step5_cases(case_source: str):
    """加载 Step5 验证案例集。返回 (cases, error)。"""
    cases = []
    cases_json = request.form.get("cases", "")
    cases_file = request.files.get("cases_file")

    if case_source == "kb":
        try:
            import knowledge_base as kb
            domain = request.form.get("kb_domain", "")
            scenario = request.form.get("kb_scenario", "")
            difficulty = request.form.get("kb_difficulty", "")
            limit = int(request.form.get("kb_limit", "10") or 10)
            kb_cases = kb.list_cases(domain=domain, scenario=scenario, difficulty=difficulty, limit=limit)
            for c in kb_cases:
                case = {
                    "case_id": c.get("case_uid", ""),
                    "description": c.get("description", ""),
                    "结论": c.get("expert_conclusion", ""),
                }
                facts = c.get("facts") or {}
                if isinstance(facts, dict):
                    case.update({k: v for k, v in facts.items() if k not in case})
                cases.append(case)
            if not cases:
                return [], "知识库案例库中无匹配案例，请先录入案例或改用上传"
            return cases, ""
        except Exception as e:
            return [], f"知识库案例加载失败: {str(e)}"

    if cases_json:
        try:
            cases = json.loads(cases_json)
        except json.JSONDecodeError:
            return [], "案例 JSON 格式错误"
    elif cases_file:
        try:
            cases = json.load(cases_file)
        except json.JSONDecodeError:
            try:
                text = cases_file.read().decode("utf-8", errors="replace")
                cases = json.loads(text)
            except json.JSONDecodeError:
                return [], "案例文件 JSON 格式错误"
    if not cases:
        return [], "请提供至少 1 个历史案例"
    return cases, ""


@app.route("/api/step5/replay", methods=["POST"])
def api_step5_replay():
    """Step5 决策回放：用 SKILL 终版判断历史案例 → 命中率 + 分歧 → 修订建议（待回流）。

    与旧 /api/validate/replay 的区别：
    - 验证对象是 SKILL.md 终版/IR 渲染（最终交付物），不是中间 Excel 文本
    - 判官模型可独立指定（judge_model 优先），避免同模型自评偏置
    - 分歧自动生成 entry 级修订建议，专家可一键回流 Step3 建议池
    """
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("judge_model", "") or request.form.get("model", "")
    case_source = (request.form.get("case_source", "") or "upload").strip()

    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    cases, err = _load_step5_cases(case_source)
    if err:
        return jsonify({"status": "error", "error": err})

    knowledge_text, knowledge_source = _resolve_skill_text_for_validation(pipeline_id)
    if not knowledge_text:
        return jsonify({"status": "error", "error": "未找到可验证的 SKILL/知识稿，请先完成智能转化（或至少完成知识萃取）"})

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": "判官模型未配置"})

    from validation_replay import (
        build_validation_prompt,
        compare_predictions,
        generate_replay_report,
        validation_to_revision_suggestions,
    )

    system_prompt, user_prompt = build_validation_prompt(knowledge_text, cases)
    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], stream=False, temperature=0.1, max_tokens=4096)
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
        raw_json = _extract_json_from_text(raw)
        try:
            predictions = json.loads(raw_json)
            if not isinstance(predictions, list):
                predictions = [{"case_id": "unknown", "prediction": raw[:200]}]
        except json.JSONDecodeError:
            predictions = [{"case_id": "unknown", "prediction": raw[:200]}]
    except Exception as e:
        return jsonify({"status": "error", "error": f"回放判官调用失败: {str(e)}"})

    comparison = compare_predictions(predictions, cases)
    report = generate_replay_report(comparison, cases, predictions)

    run_id = uuid.uuid4().hex[:8]
    report_name = f"validation_replay_{run_id}.md"
    report_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", report_name)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    result_name = f"validation_result_{run_id}.json"
    result_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", result_name)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_payload = {
        "run_id": run_id,
        "pipeline_id": pipeline_id,
        "judge_model": model_name,
        "knowledge_source": knowledge_source,
        "case_source": case_source,
        "comparison": comparison,
        "predictions": predictions,
        "ran_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    # 分歧 → entry 级修订建议（待专家回流裁决）
    suggestions = []
    suggestions_name = ""
    if comparison.get("mismatches"):
        ir = None
        sd = {}
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {}) or {}
                    break
        ir_path, _k = resolve_knowledge_ir_path(WORKSPACE, sd)
        if ir_path:
            try:
                from skill_ir import load_ir
                ir = load_ir(ir_path)
            except Exception:
                ir = None
        if ir:
            suggestions = validation_to_revision_suggestions(
                comparison["mismatches"], ir,
                llm_call_fn=_llm_call_for_interview,
                model_name=model_name,
            )
            if suggestions:
                suggestions_name = f"revision_suggestions_{run_id}.json"
                suggestions_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", suggestions_name)
                suggestions_path.parent.mkdir(parents=True, exist_ok=True)
                suggestions_path.write_text(
                    json.dumps(suggestions, ensure_ascii=False, indent=2), encoding="utf-8",
                )

    # 命中率门槛（schema quality.replay_hit_threshold）
    hit_threshold = 0.8
    try:
        if SCHEMA_PATH.exists():
            from excel_to_skill import load_scenario_config
            cfg = load_scenario_config(str(SCHEMA_PATH))
            hit_threshold = float((cfg.get("quality") or {}).get("replay_hit_threshold", 0.8))
    except Exception:
        pass
    passed = comparison["hit_rate"] >= hit_threshold

    # 持久化 step5 keys
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["step5_replay_file"] = report_name
                sd["step5_replay_url"] = f"/downloads/{report_name}"
                sd["step5_result_file"] = result_name
                sd["step5_result_url"] = f"/downloads/{result_name}"
                sd["step5_hit_rate"] = comparison["hit_rate"]
                sd["step5_case_source"] = case_source
                sd["step5_run_id"] = run_id
                if suggestions_name:
                    sd["step5_suggestions_file"] = suggestions_name
                    sd["step5_suggestions_url"] = f"/downloads/{suggestions_name}"
                else:
                    sd.pop("step5_suggestions_file", None)
                    sd.pop("step5_suggestions_url", None)
                p.setdefault("step_status", {})
                p["step_status"]["5"] = "done"
                p["current_step"] = max(p.get("current_step", 1), 5)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    # 记录到知识库验证运行表（如可用）
    try:
        import knowledge_base as kb
        kb.record_validation_run(
            pipeline_id=pipeline_id,
            skill_slug="",
            skill_version=0,
            case_uids=[str(c.get("case_id", "")) for c in cases],
            total_cases=comparison["total_cases"],
            hits=comparison["hits"],
            hit_rate=comparison["hit_rate"],
            mismatches=comparison["mismatches"],
            judge_model=model_name,
        )
    except Exception:
        pass

    return jsonify({
        "status": "ok",
        "run_id": run_id,
        "hit_rate": comparison["hit_rate"],
        "hits": comparison["hits"],
        "total": comparison["total_cases"],
        "mismatch_count": comparison["mismatch_count"],
        "mismatches": comparison["mismatches"],
        "hit_threshold": hit_threshold,
        "passed": passed,
        "knowledge_source": knowledge_source,
        "judge_model": model_name,
        "report_name": report_name,
        "download_url": f"/downloads/{report_name}",
        "result_url": f"/downloads/{result_name}",
        "suggestions": suggestions,
        "suggestions_count": len(suggestions),
        "suggestions_url": f"/downloads/{suggestions_name}" if suggestions_name else "",
    })


@app.route("/api/step5/feedback", methods=["POST"])
def api_step5_feedback():
    """验证回流：将 Step5 生成的修订建议推入 Step3 建议池，由专家裁决。"""
    data = request.get_json(force=True) or {}
    pipeline_id = data.get("pipeline_id", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    suggestions = data.get("suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        # 默认取最近一次回放生成的建议文件
        sd = {}
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {}) or {}
                    break
        sug_file = sd.get("step5_suggestions_file", "")
        if not sug_file:
            return jsonify({"status": "error", "error": "无可回流的建议，请先执行决策回放"})
        sug_path = safe_workspace_path(WORKSPACE, sug_file, must_exist=True)
        if not sug_path:
            return jsonify({"status": "error", "error": "建议文件不存在"})
        try:
            suggestions = json.loads(sug_path.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"status": "error", "error": f"建议文件解析失败: {str(e)}"})

    pushed = _push_step3_suggestions(pipeline_id, suggestions, source="validation")
    return jsonify({
        "status": "ok",
        "pushed": pushed,
        "message": f"已将 {pushed} 条修订建议回流到「知识对齐」建议池，请到第 3 步裁决",
    })


@app.route("/api/step5/golden_verify", methods=["POST"])
def api_step5_golden_verify():
    """Golden 基准验证：流水线知识 vs 黄金条目（P/R/F1），写入 verification_runs。"""
    data = request.get_json(force=True) if request.is_json else request.form
    pipeline_id = data.get("pipeline_id", "")
    scenario_id = data.get("scenario_id")
    scenario_name = data.get("scenario_name", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    try:
        items, pipeline = _read_step3_knowledge_items(pipeline_id)
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)})

    if not scenario_id and not scenario_name:
        scenario_name = pipeline.get("scenario", "") or pipeline.get("name", "")

    try:
        import golden_db
        golden_db.init_db()
        report = golden_db.verify(
            items,
            scenario_id=int(scenario_id) if scenario_id else None,
            scenario_name=scenario_name or None,
            pipeline_id=pipeline_id,
        )
    except Exception as e:
        return jsonify({"status": "error", "error": f"Golden 验证失败: {str(e)}"})

    if report.get("status") == "error":
        return jsonify(report)

    report_name = ""
    try:
        report_md = golden_db.format_report(report)
        report_name = f"validation_golden_{uuid.uuid4().hex[:8]}.md"
        golden_report_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", report_name)
        golden_report_path.parent.mkdir(parents=True, exist_ok=True)
        golden_report_path.write_text(report_md, encoding="utf-8")
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step5_golden_report_file"] = report_name
                    sd["step5_golden_report_url"] = f"/downloads/{report_name}"
                    save_pipelines(pipelines)
                    break
    except Exception:
        report_name = ""

    report["report_name"] = report_name
    report["download_url"] = f"/downloads/{report_name}" if report_name else ""
    return jsonify(report)


# ─── 外部知识库 API（知识资产 / 案例库 / 发布登记） ────────────────

@app.route("/api/kb/entries", methods=["GET"])
def api_kb_entries():
    """检索知识库条目（Step1 继承预检 / 浏览）。"""
    try:
        import knowledge_base as kb
        entries = kb.search_entries(
            domain=request.args.get("domain", ""),
            scenario=request.args.get("scenario", ""),
            query=request.args.get("q", ""),
            top_k=int(request.args.get("top_k", "20") or 20),
            status=request.args.get("status", "active"),
        )
        return jsonify({"status": "ok", "entries": entries, "total": len(entries)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"知识库检索失败: {str(e)}"})


@app.route("/api/kb/entries/import", methods=["POST"])
def api_kb_entries_import():
    """选中 KB 条目 → 标准 records（供前端注入流水线 / 调试）。"""
    data = request.get_json(force=True) or {}
    entry_uids = data.get("entry_uids") or []
    if not isinstance(entry_uids, list) or not entry_uids:
        return jsonify({"status": "error", "error": "请提供 entry_uids"})
    try:
        import knowledge_base as kb
        records = kb.import_entries_as_records([str(u) for u in entry_uids])
        return jsonify({"status": "ok", "records": records, "count": len(records)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"导入失败: {str(e)}"})


@app.route("/api/kb/publish", methods=["POST"])
def api_kb_publish():
    """Step4 发布入库：当前流水线的最新 Skill IR → kb_entries + 发布登记。"""
    data = request.get_json(force=True) or {}
    pipeline_id = data.get("pipeline_id", "")
    by = data.get("by", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})

    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break
    ir_path, _key = resolve_knowledge_ir_path(WORKSPACE, sd)
    if not ir_path:
        return jsonify({"status": "error", "error": "未找到 Skill 草稿（IR），无法发布"})

    skill_md = ""
    skill_file = sd.get("step4_skill_file", "")
    if skill_file:
        sp = safe_workspace_path(WORKSPACE, skill_file, must_exist=True)
        if sp:
            try:
                skill_md = sp.read_text(encoding="utf-8")
            except Exception:
                skill_md = ""

    try:
        import knowledge_base as kb
        from skill_ir import STATUS_PUBLISHED, load_ir, mark_status, save_ir

        ir = load_ir(ir_path)
        result = kb.publish_entries(
            ir,
            pipeline_id=pipeline_id,
            by=by,
            skill_md=skill_md,
            quality_score=None,
            replay_hit_rate=sd.get("step5_hit_rate"),
        )
        # IR 状态标记 published 并落盘新文件
        published_ir = mark_status(ir, STATUS_PUBLISHED)
        try:
            pub_name = save_ir(WORKSPACE, published_ir, pipeline_id=pipeline_id)
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p["id"] == pipeline_id:
                        sd2 = p.setdefault("step_data", {})
                        sd2["step3_aligned_file"] = pub_name
                        sd2["step3_aligned_url"] = f"/downloads/{pub_name}"
                        save_pipelines(pipelines)
                        break
        except Exception:
            pass
        result["status"] = "ok"
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": f"发布失败: {str(e)}"})


@app.route("/api/kb/entries/<entry_uid>/deprecate", methods=["POST"])
def api_kb_deprecate(entry_uid):
    data = request.get_json(force=True) or {}
    try:
        import knowledge_base as kb
        ok = kb.deprecate_entry(entry_uid, note=data.get("note", ""), by=data.get("by", ""))
        if not ok:
            return jsonify({"status": "error", "error": "条目不存在或已失效"})
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/entries/<entry_uid>/timeline", methods=["GET"])
def api_kb_timeline(entry_uid):
    try:
        import knowledge_base as kb
        return jsonify({"status": "ok", "timeline": kb.get_entry_timeline(entry_uid)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/cases", methods=["GET"])
def api_kb_list_cases():
    try:
        import knowledge_base as kb
        cases = kb.list_cases(
            domain=request.args.get("domain", ""),
            scenario=request.args.get("scenario", ""),
            difficulty=request.args.get("difficulty", ""),
            limit=int(request.args.get("limit", "20") or 20),
        )
        return jsonify({"status": "ok", "cases": cases, "total": len(cases)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/cases", methods=["POST"])
def api_kb_add_cases():
    """录入案例（单条或批量）。"""
    data = request.get_json(force=True) or {}
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raw_cases = [data]
    try:
        import knowledge_base as kb
        uids = []
        errors = []
        for c in raw_cases:
            if not isinstance(c, dict):
                continue
            try:
                uid = kb.add_case(
                    description=c.get("description", "") or c.get("场景", ""),
                    expert_conclusion=c.get("expert_conclusion", "") or c.get("结论", "") or c.get("conclusion", ""),
                    domain=c.get("domain", ""),
                    scenario=c.get("scenario", ""),
                    facts=c.get("facts") if isinstance(c.get("facts"), dict) else None,
                    expert_reasoning=c.get("expert_reasoning", ""),
                    difficulty=c.get("difficulty", ""),
                    tags=c.get("tags", ""),
                    source=c.get("source", ""),
                )
                uids.append(uid)
            except ValueError as ve:
                errors.append(str(ve))
        return jsonify({"status": "ok", "case_uids": uids, "created": len(uids), "errors": errors})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/skills", methods=["GET"])
def api_kb_skills():
    try:
        import knowledge_base as kb
        releases = kb.list_releases(
            skill_slug=request.args.get("skill_slug", ""),
            limit=int(request.args.get("limit", "20") or 20),
        )
        return jsonify({"status": "ok", "releases": releases, "total": len(releases)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


# ─── 验证知识库路由（本地知识库验证 agent-skill）───────────────────────

def _resolve_skill_text_for_verification(pipeline_id: str, skill_file: str = "") -> tuple[str, str]:
    """解析待验证 SKILL 文本：显式 skill_file > pipeline step4_skill_file > IR 渲染 > Excel。"""
    if skill_file:
        # 优先在工作区内查找
        skill_path = safe_workspace_path(WORKSPACE, skill_file, must_exist=True)
        if skill_path:
            try:
                return skill_path.read_text(encoding="utf-8"), "skill_file"
            except Exception:
                pass
        # 允许项目内相对路径（如 data/deliveries/SKILL.md）。这是项目固定资源目录的回退查找，
        # 不替代 safe_workspace_path 的安全沙箱，仅用于加载已发布产物。
        project_skill = PROJECT_DIR / skill_file
        if project_skill.exists():
            try:
                return project_skill.read_text(encoding="utf-8"), "skill_file"
            except Exception:
                pass
    return _resolve_skill_text_for_validation(pipeline_id)


@app.route("/api/kb/verification_cases", methods=["GET"])
def api_kb_list_verification_cases():
    try:
        import knowledge_base as kb
        cases = kb.list_verification_cases(
            skill_id=request.args.get("skill_id", ""),
            source=request.args.get("source", ""),
            tags=request.args.get("tags", ""),
            limit=int(request.args.get("limit", "100") or 100),
        )
        return jsonify({"status": "ok", "cases": cases, "total": len(cases)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/verification_cases", methods=["POST"])
def api_kb_add_verification_case():
    data = request.get_json(force=True) or {}
    try:
        import knowledge_base as kb
        case_uid = kb.add_verification_case(
            name=data.get("name", ""),
            input_data=data.get("input") or data.get("input_json") or {},
            description=data.get("description", ""),
            expected_output=data.get("expected_output") or data.get("expected_output_json") or {},
            tags=data.get("tags", ""),
            source=data.get("source", "manual"),
            skill_id=data.get("skill_id", ""),
        )
        return jsonify({"status": "ok", "case_uid": case_uid})
    except ValueError as ve:
        return jsonify({"status": "error", "error": str(ve)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"创建失败: {str(e)}"})


@app.route("/api/kb/verification_cases/<case_uid>", methods=["PUT"])
def api_kb_update_verification_case(case_uid):
    data = request.get_json(force=True) or {}
    try:
        import knowledge_base as kb
        updates = {}
        for k in ("name", "description", "tags", "source", "skill_id"):
            if k in data:
                updates[k] = data[k]
        if "input" in data or "input_json" in data:
            updates["input_json"] = data.get("input") or data.get("input_json") or {}
        if "expected_output" in data or "expected_output_json" in data:
            updates["expected_output_json"] = data.get("expected_output") or data.get("expected_output_json") or {}
        ok = kb.update_verification_case(case_uid, **updates)
        if not ok:
            return jsonify({"status": "error", "error": "用例不存在或无有效更新"})
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": f"更新失败: {str(e)}"})


@app.route("/api/kb/verification_cases/<case_uid>", methods=["DELETE"])
def api_kb_delete_verification_case(case_uid):
    try:
        import knowledge_base as kb
        ok = kb.delete_verification_case(case_uid)
        if not ok:
            return jsonify({"status": "error", "error": "用例不存在"})
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": f"删除失败: {str(e)}"})


@app.route("/api/kb/verification_runs", methods=["GET"])
def api_kb_list_verification_runs():
    try:
        import knowledge_base as kb
        runs = kb.list_verification_runs(
            case_id=int(request.args.get("case_id", "0") or 0),
            skill_id=request.args.get("skill_id", ""),
            limit=int(request.args.get("limit", "100") or 100),
        )
        return jsonify({"status": "ok", "runs": runs, "total": len(runs)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/kb/verification_rules", methods=["GET"])
def api_kb_list_verification_rules():
    try:
        import knowledge_base as kb
        rules = kb.list_verification_rules(
            rule_type=request.args.get("rule_type", ""),
            enabled_only=request.args.get("enabled_only", "false").lower() == "true",
            limit=int(request.args.get("limit", "100") or 100),
        )
        return jsonify({"status": "ok", "rules": rules, "total": len(rules)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/validate/run_case", methods=["POST"])
def api_validate_run_case():
    """运行单个验证用例。"""
    data = request.get_json(force=True) or {}
    case_uid = data.get("case_uid", "")
    pipeline_id = data.get("pipeline_id", "")
    skill_file = data.get("skill_file", "")
    model_name = data.get("model", "")

    if not case_uid:
        return jsonify({"status": "error", "error": "缺少 case_uid"})

    import knowledge_base as kb
    case = kb.get_verification_case(case_uid)
    if not case:
        return jsonify({"status": "error", "error": "用例不存在"})

    skill_text, source_kind = _resolve_skill_text_for_verification(pipeline_id, skill_file)
    if not skill_text:
        return jsonify({"status": "error", "error": "未找到可验证的 SKILL/知识稿"})

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        model_cfg = load_llm_config()[0] if load_llm_config() else None
    if not model_cfg:
        return jsonify({"status": "error", "error": "无可用 LLM 模型"})

    try:
        from validation_replay import run_verification_case
        result = run_verification_case(case, skill_text, model_cfg)
        run_uid = kb.add_verification_run(
            case_id=case.get("id", 0),
            skill_id=case.get("skill_id", ""),
            skill_version=pipeline_id or skill_file,
            result_status=result.get("status", ""),
            actual_output=result.get("actual_output", {}),
            diff=result.get("diff", {}),
            score=result.get("score", 0.0),
            judge_model=model_cfg.get("name", ""),
        )
        return jsonify({"status": "ok", "run_uid": run_uid, "result": result})
    except Exception as e:
        return jsonify({"status": "error", "error": f"运行失败: {str(e)}"})


@app.route("/api/validate/run_suite", methods=["POST"])
def api_validate_run_suite():
    """批量运行验证用例。"""
    data = request.get_json(force=True) or {}
    case_uids = data.get("case_uids") or []
    pipeline_id = data.get("pipeline_id", "")
    skill_file = data.get("skill_file", "")
    model_name = data.get("model", "")

    if not case_uids:
        return jsonify({"status": "error", "error": "缺少 case_uids"})

    skill_text, source_kind = _resolve_skill_text_for_verification(pipeline_id, skill_file)
    if not skill_text:
        return jsonify({"status": "error", "error": "未找到可验证的 SKILL/知识稿"})

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        model_cfg = load_llm_config()[0] if load_llm_config() else None
    if not model_cfg:
        return jsonify({"status": "error", "error": "无可用 LLM 模型"})

    import knowledge_base as kb
    cases = []
    for uid in case_uids:
        case = kb.get_verification_case(uid)
        if case:
            cases.append(case)
    if not cases:
        return jsonify({"status": "error", "error": "未找到有效用例"})

    try:
        from validation_replay import run_verification_suite, generate_verification_report
        results = run_verification_suite(cases, skill_text, model_cfg)
        run_uids = []
        for case, result in zip(cases, results):
            run_uid = kb.add_verification_run(
                case_id=case.get("id", 0),
                skill_id=case.get("skill_id", ""),
                skill_version=pipeline_id or skill_file,
                result_status=result.get("status", ""),
                actual_output=result.get("actual_output", {}),
                diff=result.get("diff", {}),
                score=result.get("score", 0.0),
                judge_model=model_cfg.get("name", ""),
            )
            run_uids.append(run_uid)
        report = generate_verification_report(results)
        return jsonify({"status": "ok", "run_uids": run_uids, "report": report, "results": results})
    except Exception as e:
        return jsonify({"status": "error", "error": f"批量运行失败: {str(e)}"})


@app.route("/api/validate/report/<run_uid>", methods=["GET"])
def api_validate_report(run_uid):
    try:
        import knowledge_base as kb
        from validation_replay import generate_verification_report, verification_report_to_markdown
        run = kb.get_verification_run(run_uid)
        if not run:
            return jsonify({"status": "error", "error": "运行记录不存在"})
        case_id = run.get("case_id", 0)
        runs = kb.list_verification_runs(case_id=case_id, limit=1000)
        report = generate_verification_report(runs)
        return jsonify({
            "status": "ok",
            "run": run,
            "report": report,
            "markdown": verification_report_to_markdown(report),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"获取报告失败: {str(e)}"})


@app.route("/api/verify/import_result_data", methods=["POST"])
def api_verify_import_result_data():
    """从 data/test-cases/ 和 golden_test.db 导入初始验证数据。"""
    data = request.get_json(force=True) or {}
    skill_id = data.get("skill_id", "")
    try:
        from tools.import_verification_data import import_result_data
        stats = import_result_data(skill_id=skill_id)
        return jsonify({"status": "ok", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "error": f"导入失败: {str(e)}"})


# ─── 多源知识融合路由 ────────────────────────────────────────

def _llm_call_for_interview(system_prompt, user_prompt, model_name):
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


@app.route("/api/step2/extract", methods=["POST"])
def step2_extract_unified():
    """统一知识萃取端点：支持单文件/多文件/文本输入，自动融合+信号报告。

    接受:
      - files[]: 多文件上传
      - text_inputs: JSON [{content, label}]
      - pipeline_id: 流水线 ID
      - model: 模型名称
      - style: 萃取风格 (默认 标准萃取)
      - content_type: 可选 "case_review" 触发案例复盘模式

    返回 JSON:
      {status, preextract_file, preextract_download_url,
       extracted_count, signal_report, source_count, dedup_count}
    """
    pipeline_id = request.form.get("pipeline_id", "")
    model_name = request.form.get("model", "")
    style = request.form.get("style", "标准萃取")
    content_type = (request.form.get("content_type", "") or "").strip()
    output_format = (request.form.get("output_format", "") or "").strip().lower()
    if output_format not in ("markdown", "excel"):
        output_format = "excel"

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return jsonify({"status": "error", "error": f"模型 '{model_name}' 不可用"})

    style = _normalize_extract_style(style)
    style_rule = EXTRACT_STYLE_RULES[style]
    template_ctx = _extract_step2_template_context(pipeline_id)
    target_columns = template_ctx.get("target_columns", [])
    stage_chain = template_ctx.get("stage_chain", [])
    step1_path = _resolve_step1_workbook_path(pipeline_id)
    skill_info = SKILL_REGISTRY.get("knowledge-extraction", {})
    skill_caps = skill_info.get("capabilities", []) if isinstance(skill_info, dict) else []
    cap_text = "；".join(skill_caps) if skill_caps else "结构化知识提取"

    # 获取所有上传的文件和文本输入
    uploaded_files = request.files.getlist("files")
    text_inputs_raw = request.form.get("text_inputs", "[]")
    try:
        text_inputs = json.loads(text_inputs_raw)
    except (json.JSONDecodeError, TypeError):
        text_inputs = []

    if not uploaded_files and not text_inputs:
        return jsonify({"status": "error", "error": "请至少上传一个文件或输入文本"})

    _debug_log("H2", "step2_extract_unified", "start", {
        "files": len(uploaded_files),
        "text_inputs": len(text_inputs),
        "style": style,
    })

    # 构造 system_prompt（含案例复盘模式）
    if content_type == "case_review":
        system_prompt = (
            f"你是一位资深银行知识工程专家，正在从「案例复盘」中同时提取两类内容：\n"
            f"萃取风格：{style}\n\n"
            f"## 任务一：识别隐性信号（重点）\n"
            f"案例复盘中的隐性知识往往不是直接说出来的。请你特别注意以下四类信号：\n"
            f"1. **规则覆盖不到的地方**：专家提到了哪些标准流程中没有的检查步骤？哪些「多余的动作」？\n"
            f"2. **情感/直觉表达**：专家用了哪些不安/不对劲/怪怪的情感词汇？这些情感背后对应了什么可观测信号？\n"
            f"3. **破例逻辑**：专家在哪次决策中突破了标准规则？他用来合理化的理由是什么？是否值得固化为例外条件？\n"
            f"4. **关系依赖**：专家提到「问了某某人」吗？那个人知道什么别人不知道的东西？\n\n"
            f"## 任务二：抽取可执行知识条目\n"
            f"同时从案例中提取以下格式的结构化知识条目。\n\n"
            f"请按以下JSON格式输出（一个数组，不要Markdown代码块，不要任何前后说明文字）：\n"
            f'[{{\"隐性信号\": \"描述一个规则覆盖不到的场景或直觉信号（一句话）\", '
            f'\"信号类型\": \"反模式|破例|直觉|关系依赖\", '
            f'\"可执行知识\": \"从这个信号中可以提炼出什么可操作的知识？\", '
            f'\"触发条件\": \"什么情况下应该特别关注这个信号？\", '
            f'\"来源\": \"来自本案例复盘的哪个部分（标题/背景/判断/结果/重来/习惯）\", '
            f'\"置信度\": \"高|中|低\"}}]\n\n'
            f"要求：\n"
            f"1. 每条隐性信号必须是完整、自包含的陈述\n"
            f"2. 优先提取反模式和破例逻辑——这些是隐性知识的关键入口\n"
            f"3. 输出条数尽量 {style_rule['min_items']}~{style_rule['max_items']} 条\n"
            f"4. 可执行知识要具体——不能只写「注意风险」，要写「注意什么风险、怎么看、看哪里」"
        )
        target_columns = ["隐性信号", "信号类型", "可执行知识", "触发条件", "来源", "置信度"]
    elif target_columns:
        target_cols_json = json.dumps(target_columns, ensure_ascii=False)
        example_obj = {k: "" for k in target_columns}
        content_key = next(
            (k for k in target_columns if any(m in k for m in ("方法", "描述", "内容", "引用"))),
            target_columns[0],
        )
        example_obj[content_key] = "（示例：从文档抽取的一条可执行知识）"
        example_json = json.dumps([example_obj], ensure_ascii=False)

        stage_hint = ""
        item_count_hint = f"输出条数尽量 {style_rule['min_items']}~{style_rule['max_items']} 条。"
        if stage_chain:
            chain_text = " → ".join(stage_chain)
            allowed_stages = "、".join(stage_chain)
            stage_hint = (
                f"\n\n【阶段因果链 — 必须遵守】\n"
                f"本模板将业务过程划分为以下阶段，阶段之间存在因果关系：{chain_text}\n"
                f"1. 「步骤」字段只能且必须填写以下四个值之一：{allowed_stages}；严禁填写文档原始章节标题（如“业务概述”“办理流程”“营销话术”等）。\n"
                f"2. 上述每个阶段都可能产生多条知识条目，不要每个阶段只输出 1 条。\n"
                f"3. 每个阶段至少输出 3 条、最多 8 条知识条目。\n"
                f"4. 条目之间要体现阶段递进：前一阶段的输出是后一阶段的输入。\n"
                f"5. 「知识引用」和「规则引用」字段必须原样保留，作为 skill 取数逻辑。\n"
                f"6. 总计输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"
            )
            item_count_hint = f"按阶段输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"

        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n"
            f"Skill能力参考：{cap_text}\n\n"
            f"风格硬规则：{style_rule['prompt_hint']}\n"
            f"请按用户上传的萃取模板抽取知识。前四列（场景/场景说明/子场景/子场景说明）已由系统填写，"
            f"JSON 只需包含下列第5列及之后的字段（键名与表头完全一致）：\n"
            f"【输出格式 — 必须严格遵守】\n"
            f"1. 只输出一个 JSON 数组，不要用 Markdown 代码块，不要写任何前后说明文字。\n"
            f"2. 数组元素为对象；每个对象的键名必须与下列列表完全一致（含连字符）：{target_cols_json}\n"
            f"3. 键名与值均使用英文双引号；无信息的字段填空字符串 \"\"。\n"
            f"4. {item_count_hint}{stage_hint}\n"
            f"5. 输出示例（结构参考，请替换为真实抽取内容）：\n{example_json}"
        )
        if _pipeline_prefers_markdown(pipeline_id) or len(target_columns) >= 8:
            system_prompt += (
                "\n\n【深度萃取 — 多语义列】\n"
                "适用条件、判断逻辑、反模式/踩坑提示、知识描述、知识引用、规则引用等长文本字段须写完整"
                "（每条通常不少于一两句），勿只填占位词；尽量让每条记录在多数语义列上都有实质内容。"
            )
    else:
        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n\n"
            f"请从以下文档中提取结构化知识条目。\n"
            f"输出格式：JSON数组，每个条目包含「知识描述」「适用条件」「判断逻辑」「知识分类」「反模式/踩坑提示」「置信度」字段。\n"
            f"不要Markdown代码块，不要前后说明文字。\n"
            f"要求：输出 5~20 条。"
        )

    scenario_meta = _pipeline_scenario_meta(pipeline_id) if pipeline_id else {}
    sub_scenarios = scenario_meta.get("sub_scenarios", [])

    # 收集所有提取源（主线程预先提取文本，Flask 文件对象非线程安全）
    errors: list[dict] = []
    sources: list[dict] = []
    for f in uploaded_files:
        try:
            doc_text = extract_text_from_file(f)
            if not doc_text or len(doc_text.strip()) < 20:
                errors.append({"source": f.filename or "未知文件", "error": "文件内容过少或为空"})
                continue
            sources.append({
                "content": doc_text[:8000],
                "label": f.filename or "上传文件",
                "source_type": "file",
            })
        except Exception as e:
            errors.append({"source": f.filename or "未知文件", "error": str(e)})

    for i, txt in enumerate(text_inputs):
        content = (txt.get("content", "") or "").strip()
        label = txt.get("label", f"文本输入 {i+1}")
        if not content or len(content) < 20:
            continue
        sources.append({
            "content": content[:8000],
            "label": label + "（文本）",
            "source_type": "text",
        })

    if not sources:
        return jsonify({"status": "error", "error": "所有来源提取均失败", "errors": errors})

    # 并行 LLM 提取
    def _extract_one(src: dict) -> dict | None:
        """提取单个来源的知识条目（线程安全，纯函数）。"""
        try:
            user_prompt = f"请从以下文档中提取知识条目：\n\n{src['content']}"
            if sub_scenarios:
                sub_names = [s.get("name", "") for s in sub_scenarios if s.get("name")]
                if sub_names:
                    user_prompt += (
                        "\n\n【子场景要求】\n"
                        "本文档涉及以下子场景，请为每个子场景分别提取知识条目：\n" +
                        "\n".join(f"- {name}" for name in sub_names) +
                        "\n\n每条知识条目必须包含一个「子场景」字段，值为上述子场景名称之一。"
                    )
            llm_result = call_llm_with_retry(
                model_cfg,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=style_rule.get("max_tokens", 4096),
                temperature=style_rule.get("temperature", 0.3),
            )
            raw = extract_assistant_content(llm_result) if isinstance(llm_result, dict) else str(llm_result)
            records, _ = _parse_extracted_items(raw)
            records = _normalize_stage_values(records, stage_chain)
            if records:
                return {"records": records, "source_label": src["label"]}
            return {"error": {"source": src["label"], "error": "提取结果为空"}}
        except Exception as e:
            return {"error": {"source": src["label"], "error": str(e)}}

    results = []
    # 当只有 1 个来源时跳过线程池开销
    if len(sources) == 1:
        outcome = _extract_one(sources[0])
        if outcome and "records" in outcome:
            results.append(outcome)
        elif outcome and "error" in outcome:
            errors.append(outcome["error"])
    else:
        max_workers = min(len(sources), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_extract_one, src): src for src in sources}
            for future in as_completed(futures):
                outcome = future.result()
                if outcome and "records" in outcome:
                    results.append(outcome)
                elif outcome and "error" in outcome:
                    errors.append(outcome["error"])

    if not results:
        return jsonify({"status": "error", "error": "所有来源提取均失败", "errors": errors})

    # 知识库继承：已沉淀条目作为一个融合源参与去重/冲突检测（KB 已有 vs 新萃取 对比信号）
    if request.form.get("kb_inherit", "") in ("1", "true", "yes"):
        try:
            import knowledge_base as kb
            meta = _pipeline_scenario_meta(pipeline_id)
            sub_scenarios = meta.get("sub_scenarios") or []
            first_sub = sub_scenarios[0].get("name", "") if sub_scenarios else ""
            kb_entries = kb.search_entries(
                domain=meta.get("domain", ""),
                scenario=meta.get("scenario_name", ""),
                sub_scenario=first_sub,
                top_k=20,
                min_score=0.3,
            )
            kb_records = kb.import_entries_as_records([e["entry_uid"] for e in kb_entries])
            if kb_records:
                results.append({"records": kb_records, "source_label": "知识库继承"})
            else:
                errors.append({
                    "source": "知识库继承",
                    "error": "当前场景知识库为空，未注入任何继承条目",
                    "level": "info",
                })
            # 记录匹配情况到 pipeline step_data
            try:
                with _pipelines_lock:
                    pipelines = load_pipelines()
                    for p in pipelines:
                        if p.get("id") == pipeline_id:
                            sd = p.get("step_data", {}) or {}
                            sd["step2_kb_match_count"] = len(kb_entries)
                            sd["step2_kb_match_domain"] = meta.get("domain", "")
                            sd["step2_kb_match_scenario"] = meta.get("scenario_name", "")
                            sd["step2_kb_match_sub_scenario"] = meta.get("sub_scenario", "")
                            save_pipelines(pipelines)
                            break
            except Exception:
                pass
        except Exception as e:
            errors.append({"source": "知识库继承", "error": str(e)})

    source_count = len(results)

    # N=1：直接写 preextract Excel
    if len(results) == 1:
        items = results[0]["records"]
        source_label = results[0]["source_label"]
        # 应用萃取风格规则（过滤/排序）
        items, extract_stats = _apply_extract_style_rules(items, style, target_columns)
        # 为单源记录生成信号报告（全量去重/冲突可能为空）
        duplicates = detect_duplicates(items)
        conflicts = detect_conflicts(items)
        signal_report = aggregate_signals(items, duplicates, conflicts)
        extracted_count = len(items)

        # 写 Excel（单源直接使用 write_preextract_excel）
        try:
            from step2_preextract import write_preextract_excel
            output_name = f"preextract_{uuid.uuid4().hex[:8]}.xlsx"
            output_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", output_name)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_preextract_excel(
                step1_path=step1_path,
                output_path=output_path,
                items=items,
                pipeline_id=pipeline_id,
                sub_scenarios=sub_scenarios,
            )
            preextract_file = output_name
            preextract_download_url = f"/downloads/{output_name}"
        except Exception as e:
            _debug_log("E", "step2_extract_unified", "excel_error", str(e)[-200:])
            preextract_file = ""
            preextract_download_url = ""

        step2_md_name, step2_md_url = "", ""
        if output_name and output_format == "markdown":
            try:
                excel_path = safe_workspace_path(WORKSPACE, output_name, must_exist=True)
                if excel_path:
                    md_name = f"preextract_{uuid.uuid4().hex[:8]}.md"
                    md_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", md_name)
                    md_path.parent.mkdir(parents=True, exist_ok=True)
                    _excel_to_markdown_file(excel_path, md_path, title=f"Step2 知识萃取")
                    step2_md_name = md_name
                    step2_md_url = f"/downloads/{md_name}"
            except Exception:
                step2_md_name, step2_md_url = "", ""

        # 持久化 pipeline step_data
        if output_name:
            _persist_step2_excel_pipeline(
                pipeline_id, output_name,
                extracted_text=json.dumps(items, ensure_ascii=False)[:2000],
                style=style,
                count=extracted_count,
                md_name=step2_md_name,
                md_url=step2_md_url,
            )
        # 保存额外字段
        try:
            with _pipelines_lock:
                pipelines = load_pipelines()
                for p in pipelines:
                    if p.get("id") == pipeline_id:
                        sd = p.get("step_data", {}) or {}
                        sd["step2_source_count"] = source_count
                        sd["step2_dedup_count"] = 0
                        save_pipelines(pipelines)
                        break
        except Exception:
            pass

        # Skill IR 草稿 v1（主产物）
        draft_info = _persist_step2_skill_draft(
            pipeline_id, items,
            signals={"signal_report": signal_report},
            origin="case_review" if content_type == "case_review" else "doc_extract",
        )

        return jsonify({
            "status": "ok",
            "preextract_file": preextract_file,
            "preextract_download_url": preextract_download_url,
            "extracted_count": extracted_count,
            "signal_report": signal_report,
            "source_count": source_count,
            "dedup_count": 0,
            "errors": errors,
            "markdown_file": step2_md_name,
            "markdown_download_url": step2_md_url,
            "skill_draft_file": draft_info.get("draft_file", ""),
            "skill_draft_url": draft_info.get("draft_url", ""),
            "skill_draft_md_file": draft_info.get("draft_md_file", ""),
            "skill_draft_md_url": draft_info.get("draft_md_url", ""),
            "skill_draft_version": draft_info.get("draft_version", 0),
        })

    # N>1：融合多源结果
    fused = merge_extraction_results(results)
    dedup_count = fused["stats"]["duplicate_count"]
    signal_report = fused.get("signal_report", {})
    # 应用萃取风格规则（过滤/排序融合后的记录）
    if fused.get("records"):
        fused["records"], extract_stats = _apply_extract_style_rules(fused["records"], style, target_columns)
    extracted_count = len(fused.get("records", []))

    # 保存融合结果 JSON
    fusion_name = f"fusion_{uuid.uuid4().hex[:8]}.json"
    try:
        fusion_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", fusion_name)
        fusion_path.parent.mkdir(parents=True, exist_ok=True)
        fusion_path.write_text(json.dumps(fused, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        fusion_name = ""

    # 生成融合 Excel
    excel_file = ""
    excel_download_url = ""
    try:
        from step2_preextract import write_fusion_to_excel
        fusion_excel_path = write_fusion_to_excel(
            fused, WORKSPACE, pipeline_id, step1_path=step1_path,
            sub_scenarios=sub_scenarios,
        )
        excel_file = Path(fusion_excel_path).name
        excel_download_url = f"/downloads/{excel_file}"
    except Exception as e:
        _debug_log("E", "step2_extract_unified", "fusion_excel_error", str(e)[-200:])

    # 保存信号报告到独立文件
    signal_report_file = ""
    signal_report_url = ""
    try:
        signal_report_name = f"signal_report_{uuid.uuid4().hex[:8]}.json"
        signal_report_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", signal_report_name)
        signal_report_path.parent.mkdir(parents=True, exist_ok=True)
        signal_report_path.write_text(
            json.dumps(signal_report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        signal_report_file = signal_report_name
        signal_report_url = f"/downloads/{signal_report_name}"
    except Exception:
        pass

    # 持久化 pipeline step_data
    multi_md_name, multi_md_url = "", ""
    if excel_file:
        if output_format == "markdown":
            try:
                excel_path = safe_workspace_path(WORKSPACE, excel_file, must_exist=True)
                if excel_path:
                    multi_md_name = f"preextract_{uuid.uuid4().hex[:8]}.md"
                    md_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", multi_md_name)
                    md_path.parent.mkdir(parents=True, exist_ok=True)
                    _excel_to_markdown_file(excel_path, md_path, title=f"Step2 知识萃取")
                    multi_md_url = f"/downloads/{multi_md_name}"
            except Exception:
                multi_md_name, multi_md_url = "", ""
        _persist_step2_excel_pipeline(
            pipeline_id, excel_file,
            extracted_text=json.dumps(fused.get("records", [])[:10], ensure_ascii=False),
            style=style,
            count=extracted_count,
            md_name=multi_md_name,
            md_url=multi_md_url,
        )
    try:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p.get("id") == pipeline_id:
                    sd = p.get("step_data", {}) or {}
                    sd["step2_signal_report_file"] = signal_report_file
                    sd["step2_signal_report_url"] = signal_report_url
                    sd["step2_source_count"] = source_count
                    sd["step2_dedup_count"] = dedup_count
                    save_pipelines(pipelines)
                    break
    except Exception:
        pass

    # Skill IR 草稿 v1（主产物，多源融合后的 records）
    draft_info = _persist_step2_skill_draft(
        pipeline_id, fused.get("records", []),
        signals={"signal_report": signal_report},
        origin="case_review" if content_type == "case_review" else "doc_extract",
    )

    return jsonify({
        "status": "ok",
        "preextract_file": excel_file,
        "preextract_download_url": excel_download_url,
        "extracted_count": extracted_count,
        "signal_report": signal_report,
        "signal_report_file": signal_report_file,
        "signal_report_url": signal_report_url,
        "source_count": source_count,
        "dedup_count": dedup_count,
        "errors": errors,
        "markdown_file": multi_md_name,
        "markdown_download_url": multi_md_url,
        "skill_draft_file": draft_info.get("draft_file", ""),
        "skill_draft_url": draft_info.get("draft_url", ""),
        "skill_draft_md_file": draft_info.get("draft_md_file", ""),
        "skill_draft_md_url": draft_info.get("draft_md_url", ""),
        "skill_draft_version": draft_info.get("draft_version", 0),
    })


@app.route("/api/step2/multi_source_extract", methods=["POST"])
def step2_multi_source_extract():
    """[已废弃] 多源知识提取 — 内部委托到统一端点 /api/step2/extract"""
    return step2_extract_unified()


@app.route("/api/step2/fuse", methods=["POST"])
def step2_fuse():
    """[已废弃] 融合已有提取结果 — 内部委托到统一端点 /api/step2/extract"""
    return step2_extract_unified()


@app.route("/api/step2/interview/start", methods=["POST"])
def step2_interview_start():
    """[已废弃] 知识深挖 — 请使用 /api/step3/interview/start"""
    return jsonify({"status": "deprecated", "message": "请使用 /api/step3/interview/start"})


@app.route("/api/step2/interview/convert", methods=["POST"])
def step2_interview_convert():
    """[已废弃] 访谈转知识条目 — 请使用 /api/step3/interview/convert"""
    return jsonify({"status": "deprecated", "message": "请使用 /api/step3/interview/convert"})


@app.route("/api/step3/interview/start", methods=["POST"])
def step3_interview_start():
    """知识深挖（Step3 访谈）：对一批知识条目启动访谈追问（自动通过 LLM 生成追问问题）。"""
    pipeline_id = request.form.get("pipeline_id", "")
    method = request.form.get("method", "case_reverse")
    model_name = request.form.get("model", "")
    knowledge_json = request.form.get("knowledge_items", "[]")

    if method not in INTERVIEW_METHODS:
        return jsonify({"status": "error", "error": f"未知追问方法: {method}，可选: {', '.join(INTERVIEW_METHODS.keys())}"})

    try:
        items = json.loads(knowledge_json)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"status": "error", "error": "knowledge_items 格式错误"})

    if not items or not isinstance(items, list):
        return jsonify({"status": "error", "error": "请提供至少一条知识条目"})

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]

    result = execute_interview_session(
        method=method,
        knowledge_items=items,
        llm_call_fn=_llm_call_for_interview,
        model_name=model_name,
    )

    # 保存到工作空间
    interview_name = f"interview_{method}_{uuid.uuid4().hex[:8]}.json"
    try:
        interview_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", interview_name)
        interview_path.parent.mkdir(parents=True, exist_ok=True)
        interview_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        interview_name = ""

    return jsonify({
        "status": "ok",
        "interview": result,
        "interview_file": interview_name,
        "interview_download_url": f"/downloads/{interview_name}" if interview_name else "",
    })


@app.route("/api/step3/interview/convert", methods=["POST"])
def step3_interview_convert():
    """知识深挖（Step3 访谈）：将已回答的访谈记录转换为知识条目。

    可选 push_to_pool=1 + pipeline_id：将回答转为 entry 级修订建议推入 Step3 建议池
    （带 entry_id 的回答 → supplement 该条目的 L2 隐性列；否则 → add 新条目），
    由专家在建议池统一裁决后应用到 Skill IR。
    """
    answers_json = request.form.get("answers", "[]")
    source_label = request.form.get("source_label", "访谈记录")
    pipeline_id = request.form.get("pipeline_id", "")
    push_to_pool = request.form.get("push_to_pool", "") in ("1", "true", "yes")

    try:
        answers = json.loads(answers_json)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"status": "error", "error": "answers 格式错误"})

    if not answers:
        return jsonify({"status": "error", "error": "请提供访谈回答"})

    records = interview_answers_to_records(answers, source_label=source_label)

    pushed = 0
    if push_to_pool and pipeline_id:
        # interview_answers_to_records 跳过空回答；用同样的过滤保证 zip 对齐
        answered = [a for a in answers if str(a.get("answer", "")).strip()]
        suggestions = []
        for ans, rec in zip(answered, records):
            entry_id = str(ans.get("entry_id") or ans.get("知识编号") or "").strip()
            category = rec.get("知识分类", "经验判断")
            if entry_id and category in ("经验判断", "适用边界", "例外情形"):
                suggestions.append({
                    "entry_id": entry_id,
                    "field": category,
                    "action": "supplement",
                    "new_value": rec.get("知识描述", ""),
                    "note": f"访谈回填（{source_label}）：{str(ans.get('question', ''))[:60]}",
                    "by": "interview",
                })
            else:
                suggestions.append({
                    "action": "add",
                    "category": category,
                    "fields": {k: v for k, v in rec.items() if not str(k).startswith("_")},
                    "note": f"访谈新增（{source_label}）",
                    "by": "interview",
                })
        pushed = _push_step3_suggestions(pipeline_id, suggestions, source="interview")

    return jsonify({
        "status": "ok",
        "records": records,
        "count": len(records),
        "pushed_to_pool": pushed,
    })


# ─── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tacit Knowledge Extraction Web App")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--workspace",
        default="",
        help="持久化工作空间目录（默认：项目内 data/workspace/；可用 WORKSPACE_DIR 环境变量覆盖）",
    )
    args = parser.parse_args()

    global WORKSPACE, CUSTOM_MODELS_PATH, PRESET_OVERRIDES_PATH, PIPELINES_PATH
    WORKSPACE = _resolve_workspace(args.workspace or None)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    CUSTOM_MODELS_PATH = WORKSPACE / "custom_models.json"
    PRESET_OVERRIDES_PATH = WORKSPACE / "preset_overrides.json"
    PIPELINES_PATH = WORKSPACE / "pipelines.json"
    _maybe_migrate_from_old_default()
    try:
        from pipeline_artifacts import organize_workspace
        organize_workspace(WORKSPACE)
    except Exception:
        pass

    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"Workspace: {WORKSPACE}")
    print(f"Frontend dir: {FRONTEND_DIR}")
    _vendor_checks = [
        FRONTEND_DIR / "vendor" / "luckysheet" / "plugins" / "js" / "plugin.js",
        FRONTEND_DIR / "vendor" / "luckysheet" / "luckysheet.umd.js",
    ]
    for p in _vendor_checks:
        if p.exists():
            print(f"  [OK] Excel editor asset: {p.relative_to(FRONTEND_DIR)}")
        else:
            print(f"  [WARN] Missing {p} — run: cd frontend && npm install luckysheet@2.1.13 jquery@3.6.4 --no-save && node ../scripts/copy-frontend-vendor.js")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
