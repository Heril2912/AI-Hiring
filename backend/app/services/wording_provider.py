"""Provider-neutral internal contract and implementations for wording providers.

Defines:
- BaseWordingProvider: Narrow, bounded domain interface.
- DisabledWordingProvider: Zero-network disabled default.
- FakeWordingProvider: Deterministic test fixture simulation.
- LocalOpenAICompatibleProvider: Secure, bounded local OpenAI-compatible HTTP adapter for LM Studio.

Strictly enforces:
- No generic chat/prompt/generation endpoints.
- No model tools, function calling, browser, ATS, filesystem or database access.
- Non-streaming transport only.
- Strict connection/read timeouts and maximum response size bounds.
- Rejection of redirects and URL credentials.
- Local-only loopback transport; zero automatic remote fallback.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx

from app.schemas.interview_blueprint import PolicyVersionReference
from app.schemas.phase3_enums import (
    AuthoringOrigin,
    ProviderCompatibilityStatus,
    ProviderEgressClass,
    ProviderErrorCode,
    ProviderOperation,
    ProviderType,
    ValidationErrorCode,
    ValidationState,
)
from app.schemas.provider_capability import (
    ProviderCapabilityRequest,
    ProviderCapabilityResponse,
    ProviderRewordResult,
)
from app.schemas.provider_profile import ProviderProfile
from app.services.destination_policy import StrictDestinationPolicy
from app.services.secret_resolver import EnvironmentSecretResolver, SecretResolutionError

from app.schemas.wording_contract import (
    PROMPT_TEMPLATE_VERSION,
    WORDING_RESPONSE_SCHEMA_VERSION,
    BoundedWordingRequest,
    BoundedWordingResponse,
    StructuredWordingVariant,
    WordingRationaleCode,
)
from app.services.wording_prompt_package import assemble_wording_messages

logger = logging.getLogger("ai_hiring.wording_provider")


class ProviderTransportError(Exception):
    """Base exception for provider transport failures."""
    def __init__(self, error_code: ProviderErrorCode, safe_message: str):
        super().__init__(safe_message)
        self.error_code = error_code
        self.safe_message = safe_message


class BaseWordingProvider(ABC):
    """Narrow provider-neutral interface separating interview domain from provider transport."""

    @abstractmethod
    async def reword_question(
        self,
        request: ProviderCapabilityRequest,
    ) -> ProviderCapabilityResponse:
        """Executes bounded question rewording or returns typed failure."""
        pass

    @abstractmethod
    async def request_wording_assistance(
        self,
        request: BoundedWordingRequest,
    ) -> BoundedWordingResponse:
        """Executes strict structured wording assistance for one authorized question."""
        pass


class DisabledWordingProvider(BaseWordingProvider):
    """Default provider mode when AI assistance is disabled.
    
    Performs zero network operations, requires no secrets, and never blocks Phase 3B.
    """

    def __init__(self, profile: Optional[ProviderProfile] = None):
        self.profile = profile

    async def reword_question(
        self,
        request: ProviderCapabilityRequest,
    ) -> ProviderCapabilityResponse:
        return ProviderCapabilityResponse(
            correlation_id=request.correlation_id,
            operation=request.operation,
            validation_state=ValidationState.BLOCKED,
            error_code=ProviderErrorCode.PROVIDER_DISABLED,
            safe_error_message="Model provider is disabled by system policy.",
            fallback_used=True,
            policy_reference=request.policy_reference,
            completed_at=datetime.now(timezone.utc),
        )

    async def request_wording_assistance(
        self,
        request: BoundedWordingRequest,
    ) -> BoundedWordingResponse:
        raise ProviderTransportError(
            error_code=ProviderErrorCode.PROVIDER_DISABLED,
            safe_message="Model provider is disabled by system policy.",
        )


class FakeWordingProvider(BaseWordingProvider):
    """Deterministic fake provider for automated unit and integration tests.
    
    Simulates successful rewording, timeout, connection failures, authentication errors,
    invalid schema responses, oversized responses, and rate limits without network traffic.
    """

    def __init__(
        self,
        simulated_mode: str = "SUCCESS",
        reworded_text_override: Optional[str] = None,
        custom_error_code: Optional[ProviderErrorCode] = None,
        custom_error_message: Optional[str] = None,
        simulated_variants_override: Optional[List[StructuredWordingVariant]] = None,
        simulated_raw_json_override: Optional[Dict[str, Any]] = None,
    ):
        self.simulated_mode = simulated_mode
        self.reworded_text_override = reworded_text_override
        self.custom_error_code = custom_error_code
        self.custom_error_message = custom_error_message
        self.simulated_variants_override = simulated_variants_override
        self.simulated_raw_json_override = simulated_raw_json_override

    async def reword_question(
        self,
        request: ProviderCapabilityRequest,
    ) -> ProviderCapabilityResponse:
        now = datetime.now(timezone.utc)

        if self.simulated_mode == "SUCCESS":
            orig_text = (
                request.reword_payload.original_text
                if request.reword_payload
                else "Default question text"
            )
            reworded = self.reworded_text_override or f"Can you describe a situation where: {orig_text}"
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.PASSED,
                error_code=None,
                safe_error_message=None,
                fallback_used=False,
                reword_result=ProviderRewordResult(
                    reworded_text=reworded,
                    intent_preserved=True,
                    authoring_origin=AuthoringOrigin.AI_ASSISTED,
                ),
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "TIMEOUT":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                safe_error_message="Simulated request timeout.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "UNAVAILABLE":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                safe_error_message="Simulated provider endpoint unavailable.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "AUTH_FAILED":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.AUTHENTICATION_FAILED,
                safe_error_message="Simulated authentication failure.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "MODEL_NOT_AVAILABLE":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.MODEL_NOT_AVAILABLE,
                safe_error_message="Simulated configured model not found on endpoint.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "OVERSIZED_RESPONSE":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_RESPONSE_TOO_LARGE,
                safe_error_message="Simulated response exceeded maximum allowed bytes.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        elif self.simulated_mode == "INVALID_RESPONSE":
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                safe_error_message="Simulated response was malformed or failed schema.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        else:
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=self.custom_error_code or ProviderErrorCode.PROVIDER_UNAVAILABLE,
                safe_error_message=self.custom_error_message or "Simulated provider error.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

    async def request_wording_assistance(
        self,
        request: BoundedWordingRequest,
    ) -> BoundedWordingResponse:
        if self.simulated_mode == "SUCCESS":
            if self.simulated_variants_override is not None:
                variants = self.simulated_variants_override
            else:
                orig_text = request.deterministic_question_text
                reworded = self.reworded_text_override or f"Could you provide an example of when: {orig_text}"
                variants = [
                    StructuredWordingVariant(
                        variant_text=reworded,
                        rationale_code=WordingRationaleCode.PROFESSIONAL_TONE,
                        referenced_identifiers=list(request.allowed_reference_ids),
                    )
                ]
            return BoundedWordingResponse(
                operation="REWORD_QUESTION",
                response_schema_version=WORDING_RESPONSE_SCHEMA_VERSION,
                variants=variants[: request.max_variants],
            )
        elif self.simulated_mode == "TIMEOUT":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                safe_message="Simulated request timeout.",
            )
        elif self.simulated_mode == "UNAVAILABLE":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                safe_message="Simulated provider endpoint unavailable.",
            )
        elif self.simulated_mode == "AUTH_FAILED":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.AUTHENTICATION_FAILED,
                safe_message="Simulated authentication failure.",
            )
        elif self.simulated_mode == "MODEL_NOT_AVAILABLE":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.MODEL_NOT_AVAILABLE,
                safe_message="Simulated configured model not found on endpoint.",
            )
        elif self.simulated_mode == "OVERSIZED_RESPONSE":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_RESPONSE_TOO_LARGE,
                safe_message="Simulated response exceeded maximum allowed bytes.",
            )
        elif self.simulated_mode == "INVALID_RESPONSE":
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                safe_message="Simulated response was malformed or failed schema.",
            )
        else:
            raise ProviderTransportError(
                error_code=self.custom_error_code or ProviderErrorCode.PROVIDER_UNAVAILABLE,
                safe_message=self.custom_error_message or "Simulated provider error.",
            )


class LocalOpenAICompatibleProvider(BaseWordingProvider):
    """Production local OpenAI-compatible HTTP adapter suitable for LM Studio.
    
    Properties:
    - Backend-only dispatch (never connects directly from client browser).
    - Enforces local loopback boundary via StrictDestinationPolicy.
    - Uses non-streaming HTTP requests with strict connect, read, and total timeouts.
    - Limits response read size to max_response_bytes.
    - Disallows HTTP redirects (follow_redirects=False).
    - Disallows cookies and raw credential URL embedding.
    - Supports optional API key bearer authentication from secret_resolver.
    - Limits concurrency via internal asyncio.Semaphore.
    - Never triggers automatic remote fallback on failure.
    """

    def __init__(
        self,
        profile: ProviderProfile,
        destination_policy: Optional[StrictDestinationPolicy] = None,
        secret_resolver: Optional[EnvironmentSecretResolver] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.profile = profile
        self.destination_policy = destination_policy or StrictDestinationPolicy(allow_remote=False)
        self.secret_resolver = secret_resolver or EnvironmentSecretResolver()
        self._custom_http_client = http_client
        self._semaphore = asyncio.Semaphore(max(1, profile.max_concurrency))

    def _resolve_headers(self) -> Dict[str, str]:
        """Constructs safe headers, injecting resolved secret if configured."""
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-Hiring-Platform/Phase3C",
        }
        if self.profile.secret_ref:
            try:
                secret_str = self.secret_resolver.resolve_secret_ref(self.profile.secret_ref)
                if secret_str:
                    headers["Authorization"] = f"Bearer {secret_str.get_secret_value()}"
            except SecretResolutionError as e:
                logger.warning("Failed to resolve secret_ref '%s': %s", self.profile.secret_ref, e.code)
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.AUTHENTICATION_FAILED,
                    safe_message=f"Secret resolution error for configured secret reference: {e.code}",
                )
        return headers

    def _validate_local_endpoint(self) -> str:
        """Validates base URL against local destination policy."""
        base_url = self.profile.base_url or "http://127.0.0.1:1234/v1"
        dest_eval = self.destination_policy.evaluate_destination(
            target_url=base_url,
            egress_class=ProviderEgressClass.LOCAL_ONLY,
        )
        if not dest_eval.is_valid:
            logger.warning("Local destination rejected by policy: %s", dest_eval.safe_error_code)
            raise ProviderTransportError(
                error_code=ProviderErrorCode.DESTINATION_DENIED,
                safe_message=f"Destination rejected: {dest_eval.safe_error_code} - {dest_eval.safe_error_message}",
            )
        return dest_eval.normalized_url or base_url.rstrip("/")

    async def _send_bounded_request(
        self,
        endpoint_url: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Transmits non-streaming payload with strict timeout and byte limit enforcement."""
        headers = self._resolve_headers()
        timeout = httpx.Timeout(
            connect=self.profile.connect_timeout_seconds,
            read=self.profile.request_timeout_seconds,
            write=self.profile.connect_timeout_seconds,
            pool=self.profile.connect_timeout_seconds,
        )

        async with self._semaphore:
            if self._custom_http_client is not None:
                client = self._custom_http_client
                should_close = False
            else:
                client = httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    cookies=None,
                    trust_env=False,  # Prevent rogue proxy env vars from redirecting loopback
                )
                should_close = True

            try:
                # Use non-streaming POST
                response = await client.post(
                    endpoint_url,
                    json=payload,
                    headers=headers,
                )

                # Check status codes
                if response.status_code == 401 or response.status_code == 403:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.AUTHENTICATION_FAILED,
                        safe_message=f"Provider returned authentication failure (HTTP {response.status_code}).",
                    )
                elif response.status_code == 404:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.MODEL_NOT_AVAILABLE,
                        safe_message=f"Provider endpoint route or model not found (HTTP {response.status_code}).",
                    )
                elif response.status_code == 429:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.PROVIDER_RATE_LIMITED,
                        safe_message="Provider returned rate limit (HTTP 429).",
                    )
                elif response.status_code >= 500:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                        safe_message=f"Provider returned server error (HTTP {response.status_code}).",
                    )
                elif response.status_code != 200:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                        safe_message=f"Provider returned unexpected status HTTP {response.status_code}.",
                    )

                # Enforce response byte limit
                content_bytes = response.content
                if len(content_bytes) > self.profile.max_response_bytes:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.PROVIDER_RESPONSE_TOO_LARGE,
                        safe_message=f"Provider response ({len(content_bytes)} bytes) exceeded bound of {self.profile.max_response_bytes} bytes.",
                    )

                try:
                    parsed_json = json.loads(content_bytes.decode("utf-8"))
                except Exception:
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                        safe_message="Provider response could not be parsed as valid JSON.",
                    )

                return parsed_json

            except httpx.ConnectTimeout:
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                    safe_message=f"Connection timeout to local provider ({self.profile.connect_timeout_seconds}s).",
                )
            except httpx.ReadTimeout:
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                    safe_message=f"Read timeout from local provider ({self.profile.request_timeout_seconds}s).",
                )
            except httpx.ConnectError:
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    safe_message="Could not connect to local provider endpoint. Ensure LM Studio server is running.",
                )
            except httpx.HTTPError as e:
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    safe_message=f"Transport error connecting to provider: {type(e).__name__}",
                )
            finally:
                if should_close:
                    await client.aclose()

    async def request_wording_assistance(
        self,
        request: BoundedWordingRequest,
    ) -> BoundedWordingResponse:
        """Executes strict structured wording assistance using the active profile."""
        if not self.profile.enabled:
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_DISABLED,
                safe_message="Target provider profile is currently disabled.",
            )

        normalized_base = self._validate_local_endpoint()
        chat_url = f"{normalized_base}/chat/completions"

        messages = assemble_wording_messages(request)

        payload = {
            "model": self.profile.model_identifier or "default",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": min(self.profile.max_output_tokens, 600),
            "stream": False,
        }

        raw_response = await self._send_bounded_request(chat_url, payload)

        choices = raw_response.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise ProviderTransportError(
                error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                safe_message="OpenAI-compatible response missing 'choices' array.",
            )

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message", {})
        raw_content = message.get("content")
        raw_reasoning = message.get("reasoning_content")

        # Normalize content
        content_str = (raw_content or "").strip()

        # Reject reasoning-only output or empty content
        if not content_str:
            if raw_reasoning or finish_reason == "length":
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.RESPONSE_CONTENT_EMPTY,
                    safe_message="The selected model used its response budget for reasoning and returned no final wording. Select a compatible Instruct model and retry. Your deterministic questions were retained.",
                )
            raise ProviderTransportError(
                error_code=ProviderErrorCode.RESPONSE_CONTENT_EMPTY,
                safe_message="OpenAI-compatible response contained null, empty, or whitespace message content.",
            )

        # Check for truncation before completing structured output
        if finish_reason == "length":
            # If the response was truncated at length boundary, it cannot be guaranteed valid
            raise ProviderTransportError(
                error_code=ProviderErrorCode.RESPONSE_TRUNCATED,
                safe_message="Model response was truncated before completing structured output (finish_reason: length).",
            )

        # Parse JSON from content (stripping markdown fences if present)
        # NEVER parse reasoning_content as final answer; only parse message.content
        clean_json_str = content_str
        if clean_json_str.startswith("```json"):
            clean_json_str = clean_json_str[7:]
        elif clean_json_str.startswith("```"):
            clean_json_str = clean_json_str[3:]
        if clean_json_str.endswith("```"):
            clean_json_str = clean_json_str[:-3]
        clean_json_str = clean_json_str.strip()

        try:
            parsed_data = json.loads(clean_json_str)
        except Exception as e:
            logger.warning("Failed to parse JSON from provider wording response: %s", e)
            raise ProviderTransportError(
                error_code=ProviderErrorCode.RESPONSE_SCHEMA_INVALID,
                safe_message="Provider response content could not be parsed into valid JSON structure.",
            )

        if not isinstance(parsed_data, dict):
            raise ProviderTransportError(
                error_code=ProviderErrorCode.RESPONSE_SCHEMA_INVALID,
                safe_message="Provider response root is not a JSON object.",
            )

        try:
            structured_response = BoundedWordingResponse.model_validate(parsed_data)
            return structured_response
        except Exception as e:
            logger.warning("Provider wording response failed schema validation: %s", e)
            raise ProviderTransportError(
                error_code=ProviderErrorCode.RESPONSE_SCHEMA_INVALID,
                safe_message=f"Provider response schema validation failed: {str(e)}",
            )

    async def reword_question(
        self,
        request: ProviderCapabilityRequest,
    ) -> ProviderCapabilityResponse:
        """Legacy capability dispatch seam maintained for backwards compatibility."""
        now = datetime.now(timezone.utc)

        if not self.profile.enabled:
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_DISABLED,
                safe_error_message="Target provider profile is currently disabled.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=now,
            )

        try:
            normalized_base = self._validate_local_endpoint()
            chat_url = f"{normalized_base}/chat/completions"

            orig_text = request.reword_payload.original_text if request.reword_payload else ""
            intent = request.reword_payload.question_intent if request.reword_payload else ""

            payload = {
                "model": self.profile.model_identifier or "default",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a professional hiring assistant. Reword interview questions clearly and concisely while preserving exact intent. No tools. No markdown."
                    },
                    {
                        "role": "user",
                        "content": f"Reword this interview question for tone: {orig_text}\nIntent: {intent}"
                    }
                ],
                "temperature": 0.2,
                "max_tokens": min(self.profile.max_output_tokens, 600),
                "stream": False,
            }

            raw_response = await self._send_bounded_request(chat_url, payload)

            choices = raw_response.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.PROVIDER_INVALID_RESPONSE,
                    safe_message="OpenAI-compatible response missing 'choices' array.",
                )

            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            message = choice.get("message", {})
            content = (message.get("content") or "").strip()
            raw_reasoning = message.get("reasoning_content")

            if not content:
                if raw_reasoning or finish_reason == "length":
                    raise ProviderTransportError(
                        error_code=ProviderErrorCode.RESPONSE_CONTENT_EMPTY,
                        safe_message="The selected model used its response budget for reasoning and returned no final wording. Select a compatible Instruct model and retry. Your deterministic questions were retained.",
                    )
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.RESPONSE_CONTENT_EMPTY,
                    safe_message="OpenAI-compatible response contained empty message content.",
                )

            if finish_reason == "length":
                raise ProviderTransportError(
                    error_code=ProviderErrorCode.RESPONSE_TRUNCATED,
                    safe_message="Model response was truncated before completion.",
                )

            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.PASSED,
                error_code=None,
                safe_error_message=None,
                fallback_used=False,
                reword_result=ProviderRewordResult(
                    reworded_text=content,
                    intent_preserved=True,
                    authoring_origin=AuthoringOrigin.AI_ASSISTED,
                ),
                policy_reference=request.policy_reference,
                completed_at=datetime.now(timezone.utc),
            )

        except ProviderTransportError as e:
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=e.error_code,
                safe_error_message=e.safe_message,
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.exception("Unexpected error in local provider dispatch: %s", e)
            return ProviderCapabilityResponse(
                correlation_id=request.correlation_id,
                operation=request.operation,
                validation_state=ValidationState.BLOCKED,
                error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                safe_error_message="Unexpected internal error during local provider dispatch.",
                fallback_used=True,
                policy_reference=request.policy_reference,
                completed_at=datetime.now(timezone.utc),
            )
