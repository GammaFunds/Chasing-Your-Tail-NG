"""Bounded, side-effect-free entrypoint for creating an inactive Kismet
eventbus runtime by delegating to the deployment module's credential-provider
factory."""

from __future__ import annotations

from collections.abc import Callable

from kismet_eventbus_deployment import (
    KismetEventbusCredentialsV1,
    KismetEventbusDeploymentManifestV1,
)
import kismet_eventbus_deployment as _deployment
import kismet_eventbus_runtime

__all__ = (
    "create_inactive_kismet_eventbus_runtime",
)


def create_inactive_kismet_eventbus_runtime(
    *,
    manifest: KismetEventbusDeploymentManifestV1,
    credential_provider: Callable[[], KismetEventbusCredentialsV1],
    ingest_timestamp_us_provider: Callable[[], int],
) -> kismet_eventbus_runtime.KismetEventbusRuntime:
    return _deployment.create_kismet_eventbus_runtime_from_credential_provider(
        manifest=manifest,
        credential_provider=credential_provider,
        ingest_timestamp_us_provider=ingest_timestamp_us_provider,
    )
