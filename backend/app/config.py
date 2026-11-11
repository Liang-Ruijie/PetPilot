from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 模型
    model_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    model_api_key: str = ""
    model_timeout: float = 60.0

    # 数据库后端：sql（本地 SQLite）/ cloudbase_rest（腾讯云网关）
    data_backend: str = "sql"
    database_url: str = "sqlite:///./data/petpilot.db"

    # 腾讯云开发（DATA_BACKEND=cloudbase_rest 时需要）
    cloudbase_env_id: str = ""
    cloudbase_api_key: str = ""
    cloudbase_rest_url: str = ""

    # 腾讯云 ASR（语音转文字，Flash 识别；密钥复用项目 2）
    asr_app_id: str = ""
    asr_secret_id: str = ""
    asr_secret_key: str = ""

    # 登录（线上邀请码；本地暂沿用固定验证码）
    fixed_login_code: str = ""
    invite_codes: str = ""  # "码1:标签1,码2:标签2"
    demo_label: str = "demo"  # 测试空间标签：每次登录自动重置成预置测试数据
    session_secret: str = ""
    session_cookie_name: str = "petpilot_session"
    session_max_age_seconds: int = 4 * 60 * 60  # 默认 4 小时
    require_login: bool = False

    # 安全 / 限流
    client_ip_header: str = "x-envoy-external-address"
    proxy_hops: int = 0
    proxy_shared_secret: str = ""
    daily_generation_limit: int = 0  # 0 = 不限制

    @property
    def invite_codes_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in (self.invite_codes or "").split(","):
            item = item.strip()
            if not item or ":" not in item:
                continue
            code, label = item.split(":", 1)
            result[code.strip()] = label.strip()
        return result

    @property
    def cloudbase_rest_url_effective(self) -> str:
        if self.cloudbase_rest_url:
            return self.cloudbase_rest_url
        if self.cloudbase_env_id:
            return f"https://{self.cloudbase_env_id}.api.tcloudbasegateway.com/v1/rdb/rest"
        return ""


settings = Settings()
