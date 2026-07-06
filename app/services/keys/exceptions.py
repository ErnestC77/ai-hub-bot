class ApiKeyNotConfiguredError(RuntimeError):
    """Ключ для запрошенной пары (provider, purpose) не задан в окружении."""


class ApiKeyPurposeNotSupportedError(RuntimeError):
    """Для этого provider нет ключа с таким purpose (опечатка в model_configs?)."""


class DevKeyUsedInProductionError(RuntimeError):
    """APP_ENV=prod, а единственный доступный ключ — *_DEV_KEY."""
