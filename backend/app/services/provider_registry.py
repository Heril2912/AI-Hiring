import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.config import Settings, get_settings
from app.schemas.phase3_enums import (
    PrivacyReviewStatus,
    ProviderCompatibilityStatus,
    ProviderEgressClass,
    ProviderOperation,
    ProviderType,
)
from app.schemas.provider_admin import (
    ActivateProviderProfileRequest,
    AdminProviderProfileResponse,
    CreateProviderProfileRequest,
    DisableProviderProfileRequest,
    ProviderCompatibilityReportResponse,
    RecruiterAIAvailabilityResponse,
    TestProviderCompatibilityRequest,
    UpdateProviderProfileRequest,
)
from app.schemas.provider_profile import ProviderProfile
from app.services.destination_policy import StrictDestinationPolicy
from app.services.provider_compatibility_service import ProviderCompatibilityService
from app.services.provider_eligibility import evaluate_provider_eligibility
from app.services.secret_resolver import EnvironmentSecretResolver


class StaleVersionError(Exception):
    """Raised when an optimistic concurrency check fails."""
    pass


class InactiveProfileUpdateError(Exception):
    """Raised when attempting to update an active profile without disabling it first."""
    pass


class IneligibleProviderError(Exception):
    """Raised when an ineligible profile is requested for activation."""
    def __init__(self, reasons: List[str]):
        super().__init__(f"Provider profile is not eligible for activation: {'; '.join(reasons)}")
        self.reasons = reasons


class RemoteEgressConfirmationRequiredError(Exception):
    """Raised when remote egress confirmation is missing during remote activation."""
    pass


class ProviderRegistry:
    """Thread-safe in-memory and settings-backed registry for ProviderProfiles.
    
    Enforces:
    - Single active profile per organization.
    - Optimistic version checks.
    - Inactive-only mutations.
    - Destination & secret validation through Phase 3A.3 policies.
    - Newly activated profiles remain NOT_TESTED unless compatibility verified.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self._lock = threading.RLock()
        self._profiles: Dict[UUID, ProviderProfile] = {}
        self._settings = settings or get_settings()
        remote_hosts = (
            [h.strip() for h in self._settings.llm_remote_allowed_hosts.split(",") if h.strip()]
            if self._settings.llm_remote_allowed_hosts
            else ["api.openai.com"]
        )
        self._destination_policy = StrictDestinationPolicy(
            allow_remote=self._settings.llm_allow_remote or True,
            remote_allowed_hosts=remote_hosts,
        )
        self._secret_resolver = EnvironmentSecretResolver()
        self._bootstrap_default_profiles()

    def _bootstrap_default_profiles(self) -> None:
        """Initializes default local and remote profiles if empty."""
        with self._lock:
            if not self._profiles:
                # Default Local Profile (LM Studio / Qwen3)
                local_profile = ProviderProfile(
                    profile_id=uuid4(),
                    display_name="Local LM Studio (Qwen3-4B)",
                    provider_type=ProviderType.LOCAL_OPENAI_COMPATIBLE,
                    base_url=self._settings.llm_base_url or "http://127.0.0.1:1234/v1",
                    model_identifier=self._settings.llm_model or "qwen3-4b-instruct",
                    secret_ref=None,
                    supported_operations=[
                        ProviderOperation.REWORD_QUESTION,
                        ProviderOperation.CREATE_BOUNDED_VARIANTS,
                    ],
                    connect_timeout_seconds=self._settings.llm_connect_timeout_seconds,
                    request_timeout_seconds=self._settings.llm_request_timeout_seconds,
                    max_input_tokens=self._settings.llm_max_input_tokens,
                    max_output_tokens=self._settings.llm_max_output_tokens,
                    egress_class=ProviderEgressClass.LOCAL_ONLY,
                    privacy_review_status=PrivacyReviewStatus.APPROVED,
                    enabled=False,
                    compatibility_status=ProviderCompatibilityStatus.NOT_TESTED,
                    model_source="Qwen/Qwen2.5-7B-Instruct-GGUF (or Qwen3-4B GGUF Q4_K_M)",
                    model_licence="Apache-2.0",
                    version=1,
                )
                self._profiles[local_profile.profile_id] = local_profile

    def list_profiles(self, organization_id: Optional[UUID] = None) -> List[ProviderProfile]:
        with self._lock:
            profiles = list(self._profiles.values())
            if organization_id:
                profiles = [p for p in profiles if p.organization_id is None or p.organization_id == organization_id]
            return sorted(profiles, key=lambda p: (not p.enabled, p.created_at))

    def get_profile(self, profile_id: UUID) -> Optional[ProviderProfile]:
        with self._lock:
            return self._profiles.get(profile_id)

    def get_active_profile(self, organization_id: Optional[UUID] = None) -> Optional[ProviderProfile]:
        with self._lock:
            for p in self._profiles.values():
                if p.enabled:
                    if organization_id is None or p.organization_id is None or p.organization_id == organization_id:
                        return p
            return None

    def create_profile(
        self,
        request: CreateProviderProfileRequest,
        actor_id: UUID,
        organization_id: Optional[UUID] = None,
    ) -> ProviderProfile:
        with self._lock:
            now = datetime.now(timezone.utc)
            # Validate destination
            if request.base_url:
                dest_res = self._destination_policy.evaluate_destination(
                    request.base_url,
                    request.egress_class,
                )
                if not dest_res.is_valid:
                    raise ValueError(f"Destination rejected: {dest_res.safe_error_message or 'Destination policy violation'}")

            # Validate secret_ref format and existence check
            if request.secret_ref:
                # Reference already formatted by Pydantic; check if resolver can attempt it
                _ = self._secret_resolver.resolve_secret_ref(request.secret_ref)

            new_profile = ProviderProfile(
                profile_id=uuid4(),
                organization_id=organization_id,
                display_name=request.display_name,
                provider_type=request.provider_type,
                api_mode=request.api_mode,
                base_url=request.base_url,
                model_identifier=request.model_identifier,
                secret_ref=request.secret_ref,
                supported_operations=request.supported_operations,
                connect_timeout_seconds=request.connect_timeout_seconds,
                request_timeout_seconds=request.request_timeout_seconds,
                max_input_tokens=request.max_input_tokens,
                max_output_tokens=request.max_output_tokens,
                max_response_bytes=request.max_response_bytes,
                max_concurrency=request.max_concurrency,
                retry_limit=request.retry_limit,
                egress_class=request.egress_class,
                privacy_review_status=PrivacyReviewStatus.APPROVED,
                enabled=False,
                compatibility_status=ProviderCompatibilityStatus.NOT_TESTED,
                tested_at=None,
                model_source=request.model_source,
                model_licence=request.model_licence,
                model_checksum=request.model_checksum,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self._profiles[new_profile.profile_id] = new_profile
            return new_profile

    def update_profile(
        self,
        profile_id: UUID,
        request: UpdateProviderProfileRequest,
        actor_id: UUID,
    ) -> ProviderProfile:
        with self._lock:
            existing = self._profiles.get(profile_id)
            if not existing:
                raise KeyError(f"Provider profile '{profile_id}' not found.")

            if existing.version != request.version:
                raise StaleVersionError(
                    f"Profile version conflict. Current version is {existing.version}, but request specified {request.version}."
                )

            if existing.enabled:
                raise InactiveProfileUpdateError("Cannot update an active provider profile. Disable it first.")

            # Validate destination
            target_url = request.base_url if request.base_url is not None else existing.base_url
            target_egress = request.egress_class if request.egress_class is not None else existing.egress_class
            if target_url:
                dest_res = self._destination_policy.evaluate_destination(target_url, target_egress)
                if not dest_res.is_valid:
                    raise ValueError(f"Destination rejected: {dest_res.safe_error_message or 'Destination policy violation'}")

            target_secret_ref = request.secret_ref if request.secret_ref is not None else existing.secret_ref
            if target_secret_ref:
                _ = self._secret_resolver.resolve_secret_ref(target_secret_ref)

            now = datetime.now(timezone.utc)
            updated = ProviderProfile(
                profile_id=existing.profile_id,
                organization_id=existing.organization_id,
                display_name=request.display_name if request.display_name is not None else existing.display_name,
                provider_type=request.provider_type if request.provider_type is not None else existing.provider_type,
                api_mode=request.api_mode if request.api_mode is not None else existing.api_mode,
                base_url=target_url,
                model_identifier=request.model_identifier if request.model_identifier is not None else existing.model_identifier,
                secret_ref=target_secret_ref,
                supported_operations=request.supported_operations if request.supported_operations is not None else existing.supported_operations,
                connect_timeout_seconds=request.connect_timeout_seconds if request.connect_timeout_seconds is not None else existing.connect_timeout_seconds,
                request_timeout_seconds=request.request_timeout_seconds if request.request_timeout_seconds is not None else existing.request_timeout_seconds,
                max_input_tokens=request.max_input_tokens if request.max_input_tokens is not None else existing.max_input_tokens,
                max_output_tokens=request.max_output_tokens if request.max_output_tokens is not None else existing.max_output_tokens,
                max_response_bytes=request.max_response_bytes if request.max_response_bytes is not None else existing.max_response_bytes,
                max_concurrency=request.max_concurrency if request.max_concurrency is not None else existing.max_concurrency,
                retry_limit=request.retry_limit if request.retry_limit is not None else existing.retry_limit,
                egress_class=target_egress,
                privacy_review_status=existing.privacy_review_status,
                enabled=False,
                compatibility_status=ProviderCompatibilityStatus.NOT_TESTED,
                tested_at=existing.tested_at,
                model_source=request.model_source if request.model_source is not None else existing.model_source,
                model_licence=request.model_licence if request.model_licence is not None else existing.model_licence,
                model_checksum=request.model_checksum if request.model_checksum is not None else existing.model_checksum,
                last_compatibility_report=existing.last_compatibility_report,
                version=existing.version + 1,
                created_at=existing.created_at,
                updated_at=now,
            )
            self._profiles[profile_id] = updated
            return updated

    async def test_compatibility(
        self,
        profile_id: UUID,
        request: TestProviderCompatibilityRequest,
        actor_id: UUID,
        compatibility_service: Optional[ProviderCompatibilityService] = None,
    ) -> ProviderCompatibilityReportResponse:
        """Runs the diagnostic compatibility test against the profile and records safe report."""
        with self._lock:
            existing = self._profiles.get(profile_id)
            if not existing:
                raise KeyError(f"Provider profile '{profile_id}' not found.")

            if existing.version != request.version:
                raise StaleVersionError(
                    f"Profile version conflict. Current version is {existing.version}, but request specified {request.version}."
                )

        runner = compatibility_service or ProviderCompatibilityService(
            destination_policy=self._destination_policy,
            secret_resolver=self._secret_resolver,
        )

        report = await runner.test_compatibility(
            profile=existing,
            timeout_override_seconds=request.timeout_override_seconds,
        )

        with self._lock:
            # Re-fetch profile to ensure safety
            current = self._profiles.get(profile_id)
            if current:
                now = datetime.now(timezone.utc)
                new_status = report.compatibility_status
                updated_profile = ProviderProfile(
                    profile_id=current.profile_id,
                    organization_id=current.organization_id,
                    display_name=current.display_name,
                    provider_type=current.provider_type,
                    api_mode=current.api_mode,
                    base_url=current.base_url,
                    model_identifier=report.model_identifier or current.model_identifier,
                    secret_ref=current.secret_ref,
                    supported_operations=current.supported_operations,
                    connect_timeout_seconds=current.connect_timeout_seconds,
                    request_timeout_seconds=current.request_timeout_seconds,
                    max_input_tokens=current.max_input_tokens,
                    max_output_tokens=current.max_output_tokens,
                    max_response_bytes=current.max_response_bytes,
                    max_concurrency=current.max_concurrency,
                    retry_limit=current.retry_limit,
                    egress_class=current.egress_class,
                    privacy_review_status=current.privacy_review_status,
                    enabled=current.enabled,
                    compatibility_status=new_status,
                    tested_at=report.tested_at,
                    model_source=current.model_source,
                    model_licence=current.model_licence,
                    model_checksum=current.model_checksum,
                    last_compatibility_report=report.model_dump(mode="json"),
                    version=current.version + 1,
                    created_at=current.created_at,
                    updated_at=now,
                )
                self._profiles[profile_id] = updated_profile

        return report

    def activate_profile(
        self,
        profile_id: UUID,
        request: ActivateProviderProfileRequest,
        actor_id: UUID,
    ) -> ProviderProfile:
        with self._lock:
            existing = self._profiles.get(profile_id)
            if not existing:
                raise KeyError(f"Provider profile '{profile_id}' not found.")

            if existing.version != request.version:
                raise StaleVersionError(
                    f"Profile version conflict. Current version is {existing.version}, but request specified {request.version}."
                )

            # Check eligibility (ignoring enabled state since it is currently disabled prior to activation)
            eligibility = evaluate_provider_eligibility(
                profile=existing,
                destination_policy=self._destination_policy,
                secret_resolver=self._secret_resolver,
                ignore_enabled_state=True,
            )
            if not eligibility.is_eligible:
                raise IneligibleProviderError(eligibility.rejection_reasons)

            # Check remote egress confirmation
            if existing.egress_class == ProviderEgressClass.APPROVED_REMOTE and not request.confirm_remote_egress:
                raise RemoteEgressConfirmationRequiredError(
                    "Explicit confirmation of remote data egress is required to activate an approved remote provider."
                )

            now = datetime.now(timezone.utc)

            # Transactionally disable all other profiles in same organization
            for p_id, p in list(self._profiles.items()):
                if p.enabled and p_id != profile_id:
                    if existing.organization_id is None or p.organization_id == existing.organization_id:
                        disabled_p = ProviderProfile(
                            profile_id=p.profile_id,
                            organization_id=p.organization_id,
                            display_name=p.display_name,
                            provider_type=p.provider_type,
                            api_mode=p.api_mode,
                            base_url=p.base_url,
                            model_identifier=p.model_identifier,
                            secret_ref=p.secret_ref,
                            supported_operations=p.supported_operations,
                            connect_timeout_seconds=p.connect_timeout_seconds,
                            request_timeout_seconds=p.request_timeout_seconds,
                            max_input_tokens=p.max_input_tokens,
                            max_output_tokens=p.max_output_tokens,
                            max_response_bytes=p.max_response_bytes,
                            max_concurrency=p.max_concurrency,
                            retry_limit=p.retry_limit,
                            egress_class=p.egress_class,
                            privacy_review_status=p.privacy_review_status,
                            enabled=False,
                            compatibility_status=p.compatibility_status,
                            tested_at=p.tested_at,
                            model_source=p.model_source,
                            model_licence=p.model_licence,
                            model_checksum=p.model_checksum,
                            last_compatibility_report=p.last_compatibility_report,
                            version=p.version + 1,
                            created_at=p.created_at,
                            updated_at=now,
                        )
                        self._profiles[p_id] = disabled_p

            # Activate target profile (preserves compatibility_status)
            activated = ProviderProfile(
                profile_id=existing.profile_id,
                organization_id=existing.organization_id,
                display_name=existing.display_name,
                provider_type=existing.provider_type,
                api_mode=existing.api_mode,
                base_url=existing.base_url,
                model_identifier=existing.model_identifier,
                secret_ref=existing.secret_ref,
                supported_operations=existing.supported_operations,
                connect_timeout_seconds=existing.connect_timeout_seconds,
                request_timeout_seconds=existing.request_timeout_seconds,
                max_input_tokens=existing.max_input_tokens,
                max_output_tokens=existing.max_output_tokens,
                max_response_bytes=existing.max_response_bytes,
                max_concurrency=existing.max_concurrency,
                retry_limit=existing.retry_limit,
                egress_class=existing.egress_class,
                privacy_review_status=existing.privacy_review_status,
                enabled=True,
                compatibility_status=existing.compatibility_status,
                tested_at=existing.tested_at,
                model_source=existing.model_source,
                model_licence=existing.model_licence,
                model_checksum=existing.model_checksum,
                last_compatibility_report=existing.last_compatibility_report,
                version=existing.version + 1,
                created_at=existing.created_at,
                updated_at=now,
            )
            self._profiles[profile_id] = activated
            return activated

    def disable_profile(
        self,
        profile_id: UUID,
        request: DisableProviderProfileRequest,
        actor_id: UUID,
    ) -> ProviderProfile:
        with self._lock:
            existing = self._profiles.get(profile_id)
            if not existing:
                raise KeyError(f"Provider profile '{profile_id}' not found.")

            if existing.version != request.version:
                raise StaleVersionError(
                    f"Profile version conflict. Current version is {existing.version}, but request specified {request.version}."
                )

            now = datetime.now(timezone.utc)
            disabled = ProviderProfile(
                profile_id=existing.profile_id,
                organization_id=existing.organization_id,
                display_name=existing.display_name,
                provider_type=existing.provider_type,
                api_mode=existing.api_mode,
                base_url=existing.base_url,
                model_identifier=existing.model_identifier,
                secret_ref=existing.secret_ref,
                supported_operations=existing.supported_operations,
                connect_timeout_seconds=existing.connect_timeout_seconds,
                request_timeout_seconds=existing.request_timeout_seconds,
                max_input_tokens=existing.max_input_tokens,
                max_output_tokens=existing.max_output_tokens,
                max_response_bytes=existing.max_response_bytes,
                max_concurrency=existing.max_concurrency,
                retry_limit=existing.retry_limit,
                egress_class=existing.egress_class,
                privacy_review_status=existing.privacy_review_status,
                enabled=False,
                compatibility_status=existing.compatibility_status,
                tested_at=existing.tested_at,
                model_source=existing.model_source,
                model_licence=existing.model_licence,
                model_checksum=existing.model_checksum,
                last_compatibility_report=existing.last_compatibility_report,
                version=existing.version + 1,
                created_at=existing.created_at,
                updated_at=now,
            )
            self._profiles[profile_id] = disabled
            return disabled

    def to_safe_admin_response(self, profile: ProviderProfile) -> AdminProviderProfileResponse:
        """Converts a ProviderProfile to safe Admin representation without secrets."""
        masked_url = None
        if profile.base_url:
            try:
                parsed = urlparse(profile.base_url)
                # Strip userinfo or query params if any
                masked_url = f"{parsed.scheme}://{parsed.hostname}{f':{parsed.port}' if parsed.port else ''}{parsed.path}"
            except Exception:
                masked_url = "[Sanitized URL]"

        secret_status = "NOT_REQUIRED"
        if profile.secret_ref:
            try:
                resolved = self._secret_resolver.resolve_secret_ref(profile.secret_ref)
                secret_status = "CONFIGURED" if resolved is not None else "MISSING"
            except Exception:
                secret_status = "MISSING"

        return AdminProviderProfileResponse(
            profile_id=profile.profile_id,
            organization_id=profile.organization_id,
            display_name=profile.display_name,
            provider_type=profile.provider_type,
            api_mode=profile.api_mode,
            base_url_masked=masked_url,
            model_identifier=profile.model_identifier,
            secret_status=secret_status,
            secret_ref_name=profile.secret_ref,
            supported_operations=profile.supported_operations,
            connect_timeout_seconds=profile.connect_timeout_seconds,
            request_timeout_seconds=profile.request_timeout_seconds,
            max_input_tokens=profile.max_input_tokens,
            max_output_tokens=profile.max_output_tokens,
            max_response_bytes=profile.max_response_bytes,
            max_concurrency=profile.max_concurrency,
            retry_limit=profile.retry_limit,
            egress_class=profile.egress_class,
            privacy_review_status=profile.privacy_review_status,
            enabled=profile.enabled,
            compatibility_status=profile.compatibility_status,
            tested_at=profile.tested_at,
            model_source=profile.model_source,
            model_licence=profile.model_licence,
            model_checksum=profile.model_checksum,
            last_compatibility_report=profile.last_compatibility_report,
            version=profile.version,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def to_recruiter_capability(self, active_profile: Optional[ProviderProfile]) -> RecruiterAIAvailabilityResponse:
        """Constructs a minimal safe capability descriptor for Recruiters."""
        if not active_profile or not active_profile.enabled or active_profile.provider_type == ProviderType.DISABLED:
            return RecruiterAIAvailabilityResponse(
                ai_enabled=False,
                provider_class="DISABLED",
                availability_label="AI Assistance Disabled",
                egress_class=ProviderEgressClass.LOCAL_ONLY,
            )

        if active_profile.provider_type == ProviderType.LOCAL_OPENAI_COMPATIBLE:
            model_label = active_profile.model_identifier or "Qwen3"
            return RecruiterAIAvailabilityResponse(
                ai_enabled=True,
                provider_class="LOCAL",
                availability_label=f"Local Engine ({model_label})",
                egress_class=ProviderEgressClass.LOCAL_ONLY,
            )

        if active_profile.provider_type == ProviderType.REMOTE_OPENAI_COMPATIBLE:
            model_label = active_profile.model_identifier or "OpenAI-Compatible"
            return RecruiterAIAvailabilityResponse(
                ai_enabled=True,
                provider_class="REMOTE",
                availability_label=f"Remote Provider ({model_label})",
                egress_class=ProviderEgressClass.APPROVED_REMOTE,
            )

        return RecruiterAIAvailabilityResponse(
            ai_enabled=False,
            provider_class="DISABLED",
            availability_label="AI Assistance Disabled",
            egress_class=ProviderEgressClass.LOCAL_ONLY,
        )


_global_provider_registry: Optional[ProviderRegistry] = None
_global_registry_lock = threading.Lock()


from fastapi import Depends


def get_provider_registry(settings: Settings = Depends(get_settings)) -> ProviderRegistry:
    """Dependency / accessor for the global ProviderRegistry."""
    global _global_provider_registry
    with _global_registry_lock:
        if _global_provider_registry is None:
            _global_provider_registry = ProviderRegistry(settings)
        return _global_provider_registry

