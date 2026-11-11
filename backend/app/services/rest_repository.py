"""数据读写的第二种实现：腾讯云开发 PostgreSQL 的 HTTPS 网关（PostgREST 语法），DATA_BACKEND=cloudbase_rest 时启用。

与本地 SqlRepository 接口一致（owner_id 在实例上，查询一律按 owner_id 过滤）。
create_* 立即 POST 并返回带 id 的记录（Prefer: return=representation）。
返回记录用 Record（带脏跟踪）：改属性后，commit() 会把被改的字段 PATCH 回数据库，
与本地 SQLAlchemy 的"改属性 → commit 落库"语义一致。

鉴权：Authorization: Bearer <CLOUDBASE_API_KEY>（服务端 API Key，管理员权限），只在后端用，不下发浏览器、
不写日志、不出现在错误信息里。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

from app.config import Settings

logger = logging.getLogger("app.rest_db")
logging.getLogger("httpx").setLevel(logging.WARNING)

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
GET_RETRIES = 1  # 只给 GET

_T_DATETIME = {"created_at", "due_at", "last_login_at"}
_T_DATE = {"occurred_at"}


class RestConfigError(RuntimeError):
    """启动时配置不全：让服务启动失败（fail fast），信息里只有变量名，没有值。"""


def _unavailable() -> Exception:
    return RuntimeError("数据库暂时连不上，请稍后重试")


def _bad_response() -> Exception:
    return RuntimeError("数据读写失败，请稍后重试")


def _iso(dt) -> str:
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return dt


class Record:
    """带脏跟踪的记录：改属性会被记下，commit() 时 PATCH 回数据库。"""

    def __init__(self, repo: "RestRepository", table: str, row_id, data: dict) -> None:
        object.__setattr__(self, "_repo", repo)
        object.__setattr__(self, "_table", table)
        object.__setattr__(self, "_id", row_id)
        for k, v in data.items():
            object.__setattr__(self, k, v)

    def __setattr__(self, key, value) -> None:
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        object.__setattr__(self, key, value)
        self._repo._mark(self._table, self._id, key, value)


def _record(repo: "RestRepository", table: str, row: dict) -> Record:
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif k in _T_DATETIME:
            try:
                out[k] = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                out[k] = v
        elif k in _T_DATE:
            try:
                out[k] = date.fromisoformat(str(v))
            except (ValueError, TypeError):
                out[k] = v
        else:
            out[k] = v
    return Record(repo, table, row.get("id"), out)


class RestRepository:
    def __init__(self, base_url: str, api_key: str, owner_id: str | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.owner_id = owner_id
        self._dirty: dict[tuple[str, int], dict] = {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=TIMEOUT, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    # ---------- 脏跟踪 ----------

    def _mark(self, table: str, row_id, key: str, value) -> None:
        if row_id is None:
            return
        self._dirty.setdefault((table, int(row_id)), {})[key] = value

    # ---------- 底层请求 ----------

    def _request(self, method: str, table: str, *, params: dict | None = None, json=None,
                 headers: dict | None = None) -> httpx.Response:
        attempts = 1 + (GET_RETRIES if method == "GET" else 0)
        for i in range(attempts):
            try:
                resp = self._client.request(method, table, params=params, json=json, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                logger.warning("rest %s %s connect failed type=%s attempt=%s", method, table, type(exc).__name__, i + 1)
                if i + 1 < attempts:
                    continue
                raise _unavailable() from None
            except httpx.HTTPError as exc:
                logger.error("rest %s %s failed type=%s", method, table, type(exc).__name__)
                raise _unavailable() from None
            if resp.status_code >= 500:
                logger.warning("rest %s %s status=%s attempt=%s", method, table, resp.status_code, i + 1)
                if i + 1 < attempts:
                    continue
                raise _unavailable()
            return resp
        raise _unavailable()

    def _check(self, resp: httpx.Response, method: str, table: str, ok: tuple[int, ...] = (200, 201, 204)) -> None:
        if resp.status_code in ok:
            return
        code = request_id = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                code = str(body.get("code", ""))[:64]
                request_id = str(body.get("requestId", ""))[:64]
        except ValueError:
            pass
        logger.error("rest %s %s status=%s code=%s request_id=%s", method, table, resp.status_code, code, request_id)
        if resp.status_code in (401, 403):
            raise _unavailable()
        raise _bad_response()

    def _rows(self, resp: httpx.Response) -> list[dict]:
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            logger.error("rest response is not a json array")
            raise _bad_response()
        return data

    def _own(self, params: dict) -> dict:
        if self.owner_id is not None:
            params = dict(params)
            params["owner_id"] = f"eq.{self.owner_id}"
        return params

    def _list(self, table: str, select: str, extra: dict | None = None, order: str | None = None,
              limit: int | None = None) -> list[Record]:
        params: dict = {"select": select}
        if extra:
            params.update(extra)
        params = self._own(params)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(int(limit))
        resp = self._request("GET", table, params=params)
        self._check(resp, "GET", table)
        return [_record(self, table, r) for r in self._rows(resp)]

    def _get_one(self, table: str, select: str, extra: dict) -> Record | None:
        params = self._own(dict(extra))
        params["select"] = select
        params["limit"] = "1"
        resp = self._request("GET", table, params=params)
        self._check(resp, "GET", table)
        rows = self._rows(resp)
        return _record(self, table, rows[0]) if rows else None

    def _insert(self, table: str, body: dict, select: str) -> Record:
        body = dict(body)
        if self.owner_id is not None:
            body["owner_id"] = self.owner_id
        now = datetime.now(timezone.utc)
        if "created_at" not in body:
            body["created_at"] = _iso(now)
        for k, v in list(body.items()):
            if isinstance(v, (date, datetime)):
                body[k] = _iso(v)
        resp = self._request("POST", table, params={"select": select}, json=body,
                             headers={"Prefer": "return=representation"})
        self._check(resp, "POST", table)
        rows = self._rows(resp)
        if len(rows) != 1:
            raise _bad_response()
        return _record(self, table, rows[0])

    def _patch(self, table: str, row_id: int, fields: dict) -> None:
        body = {}
        for k, v in fields.items():
            body[k] = _iso(v) if isinstance(v, (date, datetime)) else v
        resp = self._request("PATCH", table, params={"id": f"eq.{int(row_id)}"}, json=body)
        self._check(resp, "PATCH", table)

    # ---------- pets ----------
    def list_pets(self):
        return self._list("pets", "id,owner_id,name,created_at", order="id")

    def get_pet(self, pet_id: int):
        return self._get_one("pets", "id,owner_id,name,created_at", {"id": f"eq.{int(pet_id)}"})

    def get_pet_by_name(self, name: str):
        return self._get_one("pets", "id,owner_id,name,created_at", {"name": f"eq.{name}"})

    def create_pet(self, name: str):
        return self._insert("pets", {"name": name}, "id,owner_id,name,created_at")

    # ---------- messages ----------
    def create_message(self, role: str, content: str):
        return self._insert("messages", {"role": role, "content": content}, "id,owner_id,role,content,created_at")

    def list_recent_messages(self, limit: int = 20):
        return self._list("messages", "id,owner_id,role,content,created_at", order="id.desc", limit=limit)

    def delete_message(self, message_id: int) -> None:
        resp = self._request("DELETE", "messages", params={"id": f"eq.{int(message_id)}"})
        self._check(resp, "DELETE", "messages", ok=(200, 204))

    # ---------- facts ----------
    def list_facts(self, pet_id: int | None = None):
        extra = {"pet_id": f"eq.{int(pet_id)}"} if pet_id is not None else None
        return self._list("facts",
                          "id,owner_id,pet_id,topic,value,unit,quantity_scope,historical_current,occurred_at,polarity,change_kind,source_message_id,quote,version,created_at",
                          extra=extra, order="id.desc")

    def list_recent_facts(self, limit: int = 20):
        return self._list("facts",
                          "id,owner_id,pet_id,topic,value,unit,quantity_scope,historical_current,occurred_at,polarity,change_kind,source_message_id,quote,version,created_at",
                          order="id.desc", limit=limit)

    def create_fact(self, **kw):
        return self._insert("facts", kw,
                            "id,owner_id,pet_id,topic,value,unit,quantity_scope,historical_current,occurred_at,polarity,change_kind,source_message_id,quote,version,created_at")

    def get_fact(self, fact_id: int):
        return self._get_one("facts",
                             "id,owner_id,pet_id,topic,value,unit,quantity_scope,historical_current,occurred_at,polarity,change_kind,source_message_id,quote,version,created_at",
                             {"id": f"eq.{int(fact_id)}"})

    # ---------- held segments ----------
    def list_pending_held(self):
        return self._list("held_segments",
                          "id,owner_id,message_id,quote,topic,reason,value,unit,quantity_scope,historical_current,occurred_at,polarity,resolved_pet_id,status,created_at",
                          extra={"status": "eq.pending"}, order="id.desc")

    def create_held(self, **kw):
        return self._insert("held_segments", kw,
                            "id,owner_id,message_id,quote,topic,reason,value,unit,quantity_scope,historical_current,occurred_at,polarity,resolved_pet_id,status,created_at")

    def get_held(self, held_id: int):
        return self._get_one("held_segments",
                             "id,owner_id,message_id,quote,topic,reason,value,unit,quantity_scope,historical_current,occurred_at,polarity,resolved_pet_id,status,created_at",
                             {"id": f"eq.{int(held_id)}"})

    def get_pending_held(self, held_id: int):
        return self._get_one("held_segments",
                             "id,owner_id,message_id,quote,topic,reason,value,unit,quantity_scope,historical_current,occurred_at,polarity,resolved_pet_id,status,created_at",
                             {"id": f"eq.{int(held_id)}", "status": "eq.pending"})

    # ---------- corrections ----------
    def create_correction(self, **kw):
        return self._insert("corrections", kw,
                            "id,owner_id,fact_id,old_value,new_value,old_topic,new_topic,quote,source_message_id,created_at")

    # ---------- reminders ----------
    def list_reminders(self):
        return self._list("reminders", "id,owner_id,pet_id,quote,due_at,status,created_at", order="id.desc")

    def create_reminder(self, **kw):
        return self._insert("reminders", kw, "id,owner_id,pet_id,quote,due_at,status,created_at")

    def get_reminder(self, reminder_id: int):
        return self._get_one("reminders", "id,owner_id,pet_id,quote,due_at,status,created_at",
                             {"id": f"eq.{int(reminder_id)}"})

    # ---------- photos ----------
    def list_photos(self, pet_id: int | None = None):
        extra = {"pet_id": f"eq.{int(pet_id)}"} if pet_id is not None else None
        return self._list("photos", "id,owner_id,pet_id,filename,stored_path,description,message_id,created_at",
                          extra=extra, order="id.desc")

    def create_photo(self, **kw):
        return self._insert("photos", kw, "id,owner_id,pet_id,filename,stored_path,description,message_id,created_at")

    def get_photo(self, photo_id: int):
        return self._get_one("photos", "id,owner_id,pet_id,filename,stored_path,description,message_id,created_at",
                             {"id": f"eq.{int(photo_id)}"})

    # ---------- care summaries ----------
    def list_care_summaries(self):
        return self._list("care_summaries", "id,owner_id,pet_id,title,fact_ids,summary,stale,source_message_id,created_at",
                          order="id.desc")

    def create_care_summary(self, **kw):
        return self._insert("care_summaries", kw,
                            "id,owner_id,pet_id,title,fact_ids,summary,stale,source_message_id,created_at")

    def get_care_summary(self, summary_id: int):
        return self._get_one("care_summaries",
                             "id,owner_id,pet_id,title,fact_ids,summary,stale,source_message_id,created_at",
                             {"id": f"eq.{int(summary_id)}"})

    # ---------- weekly reviews ----------
    def list_weekly_reviews(self):
        return self._list("weekly_reviews", "id,owner_id,pet_id,title,fact_ids,summary,stale,created_at", order="id.desc")

    def create_weekly_review(self, **kw):
        return self._insert("weekly_reviews", kw, "id,owner_id,pet_id,title,fact_ids,summary,stale,created_at")

    # ---------- user ----------
    def touch_user(self, label: str) -> None:
        now = datetime.now(timezone.utc)
        resp = self._request("PATCH", "users", params={"label": f"eq.{label}"},
                             json={"last_login_at": _iso(now)}, headers={"Prefer": "return=representation"})
        self._check(resp, "PATCH", "users")
        if self._rows(resp):
            return
        resp = self._request("POST", "users", json={"label": label, "created_at": _iso(now), "last_login_at": _iso(now)},
                             headers={"Prefer": "return=minimal"})
        if resp.status_code == 409:
            return
        self._check(resp, "POST", "users")

    def clear_owner(self, owner_id: str) -> None:
        """清空某用户空间的所有业务数据（不删用户本身）。按外键依赖：先删子表（corrections 引用 facts），再删父表。"""
        tables = ["corrections", "facts", "held_segments", "reminders", "photos", "care_summaries",
                  "weekly_reviews", "messages", "pets"]
        for table in tables:
            resp = self._request("DELETE", table, params={"owner_id": f"eq.{owner_id}"})
            self._check(resp, "DELETE", table, ok=(200, 204))

    # ---------- 事务类方法 ----------

    def flush(self) -> None:
        return None

    def refresh(self, obj) -> None:
        return None

    def commit(self) -> None:
        """把脏记录（改过属性的）PATCH 回数据库，与本地 SQLAlchemy 的 commit 落库语义一致。"""
        dirty, self._dirty = self._dirty, {}
        for (table, row_id), fields in dirty.items():
            self._patch(table, row_id, fields)

    def ping(self) -> None:
        resp = self._request("GET", "pets", params={"select": "id", "limit": "1"})
        self._check(resp, "GET", "pets")


def check_config(settings: Settings) -> None:
    missing = []
    if not settings.cloudbase_api_key:
        missing.append("CLOUDBASE_API_KEY")
    if not settings.cloudbase_rest_url_effective:
        missing.append("CLOUDBASE_ENV_ID（或 CLOUDBASE_REST_URL）")
    if missing:
        raise RestConfigError("DATA_BACKEND=cloudbase_rest 但缺少环境变量：" + "、".join(missing)
                              + "。请在云托管控制台的环境变量里填写后重新部署")


def init_rest(settings: Settings, owner_id: str | None = None,
              transport: httpx.BaseTransport | None = None) -> RestRepository:
    check_config(settings)
    logger.info("db ready backend=cloudbase_rest")
    return RestRepository(settings.cloudbase_rest_url_effective, settings.cloudbase_api_key,
                          owner_id=owner_id, transport=transport)


def get_rest_repo(settings: Settings, owner_id: str | None = None) -> RestRepository:
    return init_rest(settings, owner_id)
