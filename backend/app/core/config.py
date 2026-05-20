from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vch_env: Literal["local", "staging", "production"] = "local"
    database_url: str = Field(alias="DATABASE_URL")
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=40, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_seconds: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT_SECONDS")
    database_pool_recycle_seconds: int = Field(default=1800, alias="DATABASE_POOL_RECYCLE_SECONDS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    @field_validator("database_url")
    @classmethod
    def require_postgres_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be an explicit PostgreSQL URL")
        return value

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
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    public_web_base_url: str = Field(default="https://app.virtualcarhub.com", alias="PUBLIC_WEB_BASE_URL")
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
    market_comparison_cache_ttl_hours: int = Field(
        default=48,
        alias="MARKET_COMPARISON_CACHE_TTL_HOURS",
    )
    marketcheck_snapshot_enabled: bool = Field(default=False, alias="MARKETCHECK_SNAPSHOT_ENABLED")
    snapshot_target_states_raw: str = Field(default="FL,GA,NC,SC,AL,TN,VA,TX,OH,PA", alias="SNAPSHOT_TARGET_STATES")
    snapshot_min_dom: int = Field(default=60, alias="SNAPSHOT_MIN_DOM")
    snapshot_min_year: int = Field(default=2016, alias="SNAPSHOT_MIN_YEAR")
    snapshot_min_miles: int = Field(default=300, alias="SNAPSHOT_MIN_MILES")
    snapshot_max_miles: int = Field(default=120000, alias="SNAPSHOT_MAX_MILES")
    snapshot_max_per_state: int = Field(default=50000, alias="SNAPSHOT_MAX_PER_STATE")
    marketcheck_stale_threshold_days: int = Field(default=1, alias="MARKETCHECK_STALE_THRESHOLD_DAYS")
    marketcheck_stale_cleanup_max_per_run: int = Field(default=5000, alias="MARKETCHECK_STALE_CLEANUP_MAX_PER_RUN")
    marketcheck_history_enrichment_enabled: bool = Field(default=True, alias="MARKETCHECK_HISTORY_ENRICHMENT_ENABLED")
    marketcheck_history_enrichment_interval_seconds: int = Field(default=900, alias="MARKETCHECK_HISTORY_ENRICHMENT_INTERVAL_SECONDS")
    marketcheck_history_enrichment_batch_size: int = Field(default=8, alias="MARKETCHECK_HISTORY_ENRICHMENT_BATCH_SIZE")
    marketcheck_history_enrichment_feature_min_count: int = Field(default=10, alias="MARKETCHECK_HISTORY_ENRICHMENT_FEATURE_MIN_COUNT")
    marketcheck_history_enrichment_ttl_hours: int = Field(default=168, alias="MARKETCHECK_HISTORY_ENRICHMENT_TTL_HOURS")
    marketcheck_history_enrichment_retry_hours: int = Field(default=24, alias="MARKETCHECK_HISTORY_ENRICHMENT_RETRY_HOURS")
    marketcheck_history_enrichment_startup_delay_seconds: int = Field(default=45, alias="MARKETCHECK_HISTORY_ENRICHMENT_STARTUP_DELAY_SECONDS")
    imagin_enabled: bool = Field(default=False, alias="IMAGIN_ENABLED")
    imagin_customer_id: str = Field(default="", alias="IMAGIN_CUSTOMER_ID")
    imagin_secret: str = Field(default="", alias="IMAGIN_SECRET")
    imagin_cdn_base_url: str = Field(default="https://cdn.imagin.studio/getImage", alias="IMAGIN_CDN_BASE_URL")
    imagin_country_code: str = Field(default="US", alias="IMAGIN_COUNTRY_CODE")
    imagin_default_steering: str = Field(default="left", alias="IMAGIN_DEFAULT_STEERING")
    imagin_gallery_angles: str = Field(
        default="23,21,25,17,29,13,33,09,37,05,41,01,45",
        alias="IMAGIN_GALLERY_ANGLES",
    )
    imagin_spin_enabled: bool = Field(default=False, alias="IMAGIN_SPIN_ENABLED")
    imagin_spin_start_angle: int = Field(default=200, alias="IMAGIN_SPIN_START_ANGLE")
    imagin_spin_frame_count: int = Field(default=32, alias="IMAGIN_SPIN_FRAME_COUNT")

    # ChromeData / J.D. Power vehicle identity + media services
    chromedata_enabled: bool = Field(default=False, alias="CHROMEDATA_ENABLED")
    chromedata_locale: str = Field(default="en_US", alias="CHROMEDATA_LOCALE")
    chromedata_country: str = Field(default="US", alias="CHROMEDATA_COUNTRY")
    chromedata_profile_key: str = Field(default="", alias="CHROMEDATA_PROFILE_KEY")
    chromedata_api_key: str = Field(default="", alias="CHROMEDATA_API_KEY")
    chromedata_api_secret: str = Field(default="", alias="CHROMEDATA_API_SECRET")
    chromedata_cvd_base_url: str = Field(default="", alias="CHROMEDATA_CVD_BASE_URL")
    chromedata_vss_base_url: str = Field(default="", alias="CHROMEDATA_VSS_BASE_URL")
    chromedata_media_base_url: str = Field(
        default="https://media.chromedata.com/MediaGallery/service",
        alias="CHROMEDATA_MEDIA_BASE_URL",
    )
    chromedata_media_username: str = Field(default="", alias="CHROMEDATA_MEDIA_USERNAME")
    chromedata_media_password: str = Field(default="", alias="CHROMEDATA_MEDIA_PASSWORD")

    # EVOX Images API
    evox_enabled: bool = Field(default=False, alias="EVOX_ENABLED")
    evox_api_key: str = Field(default="", alias="EVOX_API_KEY")
    evox_api_base_url: str = Field(
        default="https://api.evoximages.com/api/v1", alias="EVOX_API_BASE_URL"
    )
    evox_prefer_webp: str = Field(default="true", alias="EVOX_PREFER_WEBP")

    # OVE Inventory Staleness
    ove_stale_threshold_days: int = Field(default=5, alias="OVE_STALE_THRESHOLD_DAYS")
    ove_stale_cleanup_max_per_run: int = Field(default=5000, alias="OVE_STALE_CLEANUP_MAX_PER_RUN")
    ove_stale_cleanup_enabled: bool = Field(default=True, alias="OVE_STALE_CLEANUP_ENABLED")
    ove_stale_cleanup_interval_seconds: int = Field(default=7200, alias="OVE_STALE_CLEANUP_INTERVAL_SECONDS")
    ove_stale_cleanup_startup_delay_seconds: int = Field(default=120, alias="OVE_STALE_CLEANUP_STARTUP_DELAY_SECONDS")
    ove_unavailable_retention_days: int = Field(default=14, alias="OVE_UNAVAILABLE_RETENTION_DAYS")
    ove_unavailable_cleanup_max_per_run: int = Field(default=5000, alias="OVE_UNAVAILABLE_CLEANUP_MAX_PER_RUN")

    # OVE Operational Health thresholds (minutes). Used by /inventory/ove/health
    # to classify staleness into ok / warning / critical bands.
    ove_health_snapshot_warning_minutes: int = Field(default=360, alias="OVE_HEALTH_SNAPSHOT_WARNING_MINUTES")
    ove_health_snapshot_critical_minutes: int = Field(default=720, alias="OVE_HEALTH_SNAPSHOT_CRITICAL_MINUTES")
    ove_health_heartbeat_warning_minutes: int = Field(default=5, alias="OVE_HEALTH_HEARTBEAT_WARNING_MINUTES")
    ove_health_heartbeat_critical_minutes: int = Field(default=15, alias="OVE_HEALTH_HEARTBEAT_CRITICAL_MINUTES")
    # Default raised to $4000 to filter out fees-only OVE listings (e.g.,
    # $3249 = auction fees with $0 vehicle cost). Real auction vehicles
    # start well above this, so legitimate inventory is unaffected.
    ove_min_vehicle_price: float = Field(default=4000.0, alias="OVE_MIN_VEHICLE_PRICE")
    # Snapshot replacement safety guard. The scraper sends one full deduped
    # snapshot per cycle. If incoming count >= this ratio of existing available
    # OVE vehicles, the server does a full replace. Reject if below this to
    # guard against truncated uploads.
    ove_snapshot_min_ratio: float = Field(default=0.8, alias="OVE_SNAPSHOT_MIN_RATIO")
    ove_snapshot_min_count: int = Field(default=100, alias="OVE_SNAPSHOT_MIN_COUNT")

    # NHTSA VIN Decoding (free, no key required)
    vin_decode_enabled: bool = Field(default=True, alias="VIN_DECODE_ENABLED")
    nhtsa_api_base_url: str = Field(
        default="https://vpic.nhtsa.dot.gov/api", alias="NHTSA_API_BASE_URL"
    )

    # Graphiti knowledge graph (on MC VPS)
    graphiti_url: str = Field(default="http://mc-vps:8001", alias="GRAPHITI_URL")

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
    ghl_contact_cf_vch_user_id: str = Field(default="", alias="GHL_CONTACT_CF_VCH_USER_ID")
    ghl_contact_cf_vch_deal_id: str = Field(default="", alias="GHL_CONTACT_CF_VCH_DEAL_ID")
    ghl_contact_cf_vch_deal_stage: str = Field(default="", alias="GHL_CONTACT_CF_VCH_DEAL_STAGE")
    ghl_contact_cf_vch_funding_state: str = Field(default="", alias="GHL_CONTACT_CF_VCH_FUNDING_STATE")
    ghl_contact_cf_vch_selected_vin: str = Field(default="", alias="GHL_CONTACT_CF_VCH_SELECTED_VIN")
    ghl_contact_cf_vch_profile_tier: str = Field(default="", alias="GHL_CONTACT_CF_VCH_PROFILE_TIER")
    ghl_contact_cf_vch_profile_completion_pct: str = Field(
        default="",
        alias="GHL_CONTACT_CF_VCH_PROFILE_COMPLETION_PCT",
    )
    ghl_contact_cf_vch_preapproved: str = Field(default="", alias="GHL_CONTACT_CF_VCH_PREAPPROVED")
    ghl_contact_cf_vch_preapproval_amount: str = Field(default="", alias="GHL_CONTACT_CF_VCH_PREAPPROVAL_AMOUNT")
    ghl_contact_cf_vch_preapproval_until: str = Field(default="", alias="GHL_CONTACT_CF_VCH_PREAPPROVAL_UNTIL")
    ghl_contact_cf_vch_cr_last_requested_at: str = Field(
        default="",
        alias="GHL_CONTACT_CF_VCH_CR_LAST_REQUESTED_AT",
    )
    ghl_contact_cf_vch_cr_last_completed_at: str = Field(
        default="",
        alias="GHL_CONTACT_CF_VCH_CR_LAST_COMPLETED_AT",
    )
    ghl_contact_cf_vch_cr_last_url: str = Field(default="", alias="GHL_CONTACT_CF_VCH_CR_LAST_URL")
    ghl_contact_cf_routeone_app_id: str = Field(default="", alias="GHL_CONTACT_CF_ROUTEONE_APP_ID")
    ghl_contact_cf_vch_lender_name: str = Field(default="", alias="GHL_CONTACT_CF_VCH_LENDER_NAME")
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

    # SendGrid email (password reset, notifications)
    sendgrid_api_key: str = Field(default="", alias="SENDGRID_API_KEY")
    sendgrid_from_email: str = Field(default="noreply@virtualcarhub.com", alias="SENDGRID_FROM_EMAIL")
    sendgrid_from_name: str = Field(default="Virtual CarHub", alias="SENDGRID_FROM_NAME")
    password_reset_expire_minutes: int = Field(default=30, alias="PASSWORD_RESET_EXPIRE_MINUTES")
    email_login_expire_minutes: int = Field(default=1440, alias="EMAIL_LOGIN_EXPIRE_MINUTES")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_cr_review_mode: Literal["disabled", "inline", "async"] = Field(
        default="disabled",
        alias="OPENAI_CR_REVIEW_MODE",
    )
    openai_cr_review_model: str = Field(
        default="gpt-5.4-mini-2026-03-17",
        alias="OPENAI_CR_REVIEW_MODEL",
    )
    openai_cr_review_auto_apply_confidence: float = Field(
        default=0.82,
        alias="OPENAI_CR_REVIEW_CONFIDENCE_AUTO_APPLY",
    )
    openai_cr_review_input_char_limit: int = Field(
        default=14000,
        alias="OPENAI_CR_REVIEW_INPUT_CHAR_LIMIT",
    )
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
    def snapshot_target_states(self) -> list[str]:
        seen: set[str] = set()
        states: list[str] = []
        for raw_state in self.snapshot_target_states_raw.split(","):
            state = raw_state.strip().upper()
            if len(state) != 2 or state in seen:
                continue
            seen.add(state)
            states.append(state)
        return states

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

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_imagin(self) -> bool:
        return self.imagin_enabled and bool(self.imagin_customer_id)

    @property
    def has_chromedata_vin(self) -> bool:
        return (
            self.chromedata_enabled
            and bool(self.chromedata_cvd_base_url)
            and bool(self.chromedata_api_key)
            and bool(self.chromedata_api_secret)
        )

    @property
    def has_chromedata_vss(self) -> bool:
        return (
            self.chromedata_enabled
            and bool(self.chromedata_vss_base_url)
            and bool(self.chromedata_api_key)
            and bool(self.chromedata_api_secret)
        )

    @property
    def has_chromedata_media(self) -> bool:
        return (
            self.chromedata_enabled
            and bool(self.chromedata_media_base_url)
            and bool(self.chromedata_media_username)
            and bool(self.chromedata_media_password)
        )

    @property
    def has_evox(self) -> bool:
        return self.evox_enabled and bool(self.evox_api_key)

    @property
    def has_sendgrid(self) -> bool:
        return bool(self.sendgrid_api_key)

    @property
    def has_vin_decode(self) -> bool:
        return self.vin_decode_enabled

    @property
    def imagin_gallery_angle_list(self) -> list[str]:
        return [value.strip() for value in self.imagin_gallery_angles.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
