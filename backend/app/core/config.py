from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vch_env: Literal["local", "staging", "production"] = "local"
    database_url: str = Field(default="sqlite:///./virtual_carhub.db", alias="DATABASE_URL")
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=40, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_seconds: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT_SECONDS")
    database_pool_recycle_seconds: int = Field(default=1800, alias="DATABASE_POOL_RECYCLE_SECONDS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret_key: str = Field(default="dev-secret", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_expire_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("JWT_ACCESS_EXPIRE_MINUTES", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES"),
    )
    jwt_refresh_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices("JWT_REFRESH_EXPIRE_DAYS", "JWT_REFRESH_TOKEN_EXPIRE_DAYS"),
    )

    service_token: str = Field(default="dev-service-token", alias="SERVICE_TOKEN")
    wordpress_export_bearer_token: str = Field(default="", alias="WORDPRESS_EXPORT_BEARER_TOKEN")
    wordpress_export_topup_enabled: bool = Field(default=False, alias="WORDPRESS_EXPORT_TOPUP_ENABLED")
    wordpress_export_topup_min_results: int = Field(default=35, alias="WORDPRESS_EXPORT_TOPUP_MIN_RESULTS")
    wordpress_export_topup_zip: str = Field(default="", alias="WORDPRESS_EXPORT_TOPUP_ZIP")
    wordpress_export_topup_radius: int = Field(default=25, alias="WORDPRESS_EXPORT_TOPUP_RADIUS")
    wordpress_export_topup_limit: int = Field(default=200, alias="WORDPRESS_EXPORT_TOPUP_LIMIT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    public_web_base_url: str = Field(default="https://virtualcarhub.com", alias="PUBLIC_WEB_BASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file_path: str = Field(default="/var/log/virtual-carhub/backend.log", alias="LOG_FILE_PATH")
    object_storage_provider: Literal["none", "s3"] = Field(default="none", alias="OBJECT_STORAGE_PROVIDER")
    object_storage_public_base_url: str = Field(default="", alias="OBJECT_STORAGE_PUBLIC_BASE_URL")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_s3_endpoint_url: str = Field(default="", alias="AWS_S3_ENDPOINT_URL")
    aws_cloudfront_domain: str = Field(default="", alias="AWS_CLOUDFRONT_DOMAIN")
    s3_assets_bucket: str = Field(default="", alias="S3_ASSETS_BUCKET")
    s3_marketcheck_cache_bucket: str = Field(default="", alias="S3_MARKETCHECK_CACHE_BUCKET")
    marketcheck_cache_enabled: bool = Field(default=False, alias="MARKETCHECK_CACHE_ENABLED")
    marketcheck_cache_ttl_detail_seconds: int = Field(default=21600, alias="MARKETCHECK_CACHE_TTL_DETAIL_SECONDS")
    marketcheck_cache_ttl_search_seconds: int = Field(default=900, alias="MARKETCHECK_CACHE_TTL_SEARCH_SECONDS")
    marketcheck_cache_ttl_facets_seconds: int = Field(default=3600, alias="MARKETCHECK_CACHE_TTL_FACETS_SECONDS")
    marketcheck_cache_ttl_price_seconds: int = Field(default=86400, alias="MARKETCHECK_CACHE_TTL_PRICE_SECONDS")

    # Live integration toggles
    marketcheck_live_enabled: bool = Field(default=False, alias="MARKETCHECK_LIVE_ENABLED")
    ghl_live_enabled: bool = Field(default=False, alias="GHL_LIVE_ENABLED")
    docusign_live_enabled: bool = Field(default=False, alias="DOCUSIGN_LIVE_ENABLED")
    telnyx_live_enabled: bool = Field(default=False, alias="TELNYX_LIVE_ENABLED")
    ghl_documents_enabled: bool = Field(default=True, alias="GHL_DOCUMENTS_ENABLED")
    ghl_custom_objects_enabled: bool = Field(default=False, alias="GHL_CUSTOM_OBJECTS_ENABLED")

    # Core integration endpoints and keys
    marketcheck_api_key: str = Field(default="", alias="MARKETCHECK_API_KEY")
    marketcheck_api_secret: str = Field(default="", alias="MARKETCHECK_API_SECRET")
    marketcheck_price_api_key: str = Field(default="", alias="MARKETCHECK_PRICE_API_KEY")
    marketcheck_api_base_url: str = Field(default="https://api.marketcheck.com/v2", alias="MARKETCHECK_API_BASE_URL")

    ghl_api_key: str = Field(default="", alias="GHL_API_KEY")
    ghl_location_id: str = Field(default="", alias="GHL_LOCATION_ID")
    ghl_webhook_secret: str = Field(default="", alias="GHL_WEBHOOK_SECRET")
    ghl_api_base_url: str = Field(default="https://services.leadconnectorhq.com", alias="GHL_API_BASE_URL")
    ghl_api_version: str = Field(default="2021-07-28", alias="GHL_API_VERSION")
    ghl_agency_api_key: str = Field(
        default="", validation_alias=AliasChoices("GHL_AGENCY_API_KEY", "HL_AGENCY_API_KEY")
    )
    ghl_company_id: str = Field(default="", alias="GHL_COMPANY_ID")
    ghl_private_token: str = Field(default="", alias="GHL_PRIVATE_TOKEN")
    ghl_deals_pipeline_id: str = Field(default="", alias="GHL_DEALS_PIPELINE_ID")
    ghl_stage_new_deal_submitted: str = Field(
        default="",
        validation_alias=AliasChoices("GHL_DEALS_STAGE_NEW_DEAL_SUBMITTED", "GHL_DEALS_STAGE_NEW"),
    )
    ghl_stage_conditional_approval: str = Field(default="", alias="GHL_DEALS_STAGE_CONDITIONAL_APPROVAL")
    ghl_stage_final_approval: str = Field(default="", alias="GHL_DEALS_STAGE_FINAL_APPROVAL")
    ghl_stage_documents_ready: str = Field(default="", alias="GHL_DEALS_STAGE_DOCUMENTS_READY")
    ghl_stage_original_docs_qc_review: str = Field(default="", alias="GHL_DEALS_STAGE_ORIGINAL_DOCS_QC_REVIEW")
    ghl_stage_deal_funded: str = Field(
        default="",
        validation_alias=AliasChoices("GHL_DEALS_STAGE_DEAL_FUNDED", "GHL_DEALS_STAGE_FUNDED"),
    )
    ghl_stage_declined: str = Field(default="", alias="GHL_DEALS_STAGE_DECLINED")
    ghl_return_authorization_template_id: str = Field(
        default="", alias="GHL_RETURN_AUTHORIZATION_TEMPLATE_ID"
    )
    ghl_documents_send_path: str = Field(
        default="/proposals/templates/send",
        alias="GHL_DOCUMENTS_SEND_PATH",
    )
    ghl_vehicles_object_key: str = Field(default="vehicles", alias="GHL_VEHICLES_OBJECT_KEY")
    ghl_loan_cases_object_key: str = Field(default="loan_cases", alias="GHL_LOAN_CASES_OBJECT_KEY")
    ghl_return_cases_object_key: str = Field(default="return_cases", alias="GHL_RETURN_CASES_OBJECT_KEY")

    docusign_integration_key: str = Field(default="", alias="DOCUSIGN_INTEGRATION_KEY")
    docusign_secret_key: str = Field(default="", alias="DOCUSIGN_SECRET_KEY")
    docusign_account_id: str = Field(default="", alias="DOCUSIGN_ACCOUNT_ID")
    docusign_base_url: str = Field(default="https://demo.docusign.net/restapi", alias="DOCUSIGN_BASE_URL")

    telnyx_api_key: str = Field(default="", alias="TELNYX_API_KEY")
    telnyx_phone_number: str = Field(default="", alias="TELNYX_PHONE_NUMBER")
    telnyx_base_url: str = Field(default="https://api.telnyx.com/v2", alias="TELNYX_BASE_URL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    datadog_api_key: str = Field(default="", alias="DATADOG_API_KEY")
    mixpanel_token: str = Field(default="", alias="MIXPANEL_TOKEN")
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # PRD rate limits
    buyer_rate_limit_per_minute: int = Field(default=100, alias="BUYER_RATE_LIMIT_PER_MINUTE")
    agent_rate_limit_per_minute: int = Field(default=1000, alias="AGENT_RATE_LIMIT_PER_MINUTE")
    rate_limit_redis_prefix: str = Field(default="vch:ratelimit", alias="RATE_LIMIT_REDIS_PREFIX")
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    metrics_path: str = Field(default="/metrics", alias="METRICS_PATH")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def has_marketcheck(self) -> bool:
        return self.marketcheck_live_enabled and bool(self.marketcheck_api_key)

    @property
    def has_ghl(self) -> bool:
        return self.ghl_live_enabled and bool(self.ghl_api_key)

    @property
    def has_docusign(self) -> bool:
        return self.docusign_live_enabled and bool(self.docusign_integration_key)

    @property
    def has_telnyx(self) -> bool:
        return self.telnyx_live_enabled and bool(self.telnyx_api_key)

    @property
    def has_ghl_documents(self) -> bool:
        return (
            self.has_ghl
            and self.ghl_documents_enabled
            and bool(self.ghl_return_authorization_template_id)
        )

    @property
    def has_ghl_custom_objects(self) -> bool:
        return self.has_ghl and self.ghl_custom_objects_enabled

    @property
    def has_s3_assets(self) -> bool:
        return self.object_storage_provider == "s3" and bool(self.s3_assets_bucket)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
