"""Environment-credential provider for Kismet eventbus deployment.

This module provides a credential provider that reads Base64-encoded
credentials from a caller-supplied environment mapping.  It performs
no discovery, I/O, filesystem, network, or runtime activation.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping

from kismet_eventbus_deployment import KismetEventbusCredentialsV1

__all__ = (
    "create_kismet_eventbus_environment_credential_provider",
)

_AUTHORIZATION_KEY = "CYT_KISMET_AUTHORIZATION_HEADER_B64"
_HMAC_KEY = "CYT_OBSERVATION_HMAC_KEY_B64"


def create_kismet_eventbus_environment_credential_provider(
    *,
    environment: Mapping[str, str],
) -> Callable[[], KismetEventbusCredentialsV1]:
    if not isinstance(environment, Mapping):
        raise TypeError("environment must be a Mapping")

    def _provider() -> KismetEventbusCredentialsV1:
        _missing = False
        try:
            auth_value = environment[_AUTHORIZATION_KEY]
        except KeyError:
            _missing = True

        try:
            hmac_value = environment[_HMAC_KEY]
        except KeyError:
            _missing = True

        if _missing:
            raise ValueError("environment credentials missing")

        if type(auth_value) is not str:
            raise ValueError("environment credentials invalid")
        if type(hmac_value) is not str:
            raise ValueError("environment credentials invalid")

        _invalid = False
        try:
            auth_bytes = base64.b64decode(auth_value, validate=True)
        except Exception:
            _invalid = True

        try:
            hmac_bytes = base64.b64decode(hmac_value, validate=True)
        except Exception:
            _invalid = True

        if _invalid:
            raise ValueError("environment credentials invalid")

        if base64.b64encode(auth_bytes).decode("ascii") != auth_value:
            raise ValueError("environment credentials invalid")
        if base64.b64encode(hmac_bytes).decode("ascii") != hmac_value:
            raise ValueError("environment credentials invalid")

        return KismetEventbusCredentialsV1(
            authorization_header_value=auth_bytes,
            hmac_key=hmac_bytes,
        )

    return _provider
