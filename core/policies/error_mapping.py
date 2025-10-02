"""
Error Mapping — User-friendly messages for all error codes
Maps technical errors to clear, actionable user messages
"""

from typing import Dict, Tuple
from dataclasses import dataclass


@dataclass
class ErrorMapping:
    """Error code mapping to user/tech messages"""
    user_message: str
    tech_message: str
    retryable: bool


# Phase 1 Error Codes and Messages
ERROR_MAPPINGS: Dict[str, ErrorMapping] = {
    # Validation Errors
    "VALIDATION_FAILED": ErrorMapping(
        user_message="Не удалось обработать ответ из-за несоответствия формата",
        tech_message="Response validation failed: schema mismatch or constraint violation",
        retryable=False
    ),
    "EVIDENCE_MISSING": ErrorMapping(
        user_message="Недостаточно источников для подтверждения выводов",
        tech_message="One or more insights missing required evidence_refs",
        retryable=True
    ),
    "PII_DETECTED": ErrorMapping(
        user_message="Обнаружены конфиденциальные данные в ответе",
        tech_message="PII patterns detected in response text",
        retryable=False
    ),
    "UNSAFE_DOMAIN": ErrorMapping(
        user_message="Источник из недоверенного домена",
        tech_message="Evidence from blacklisted or unsafe domain",
        retryable=False
    ),
    "LENGTH_EXCEEDED": ErrorMapping(
        user_message="Ответ превышает допустимую длину",
        tech_message="Response text exceeds maximum length constraints",
        retryable=True
    ),

    # Data Errors
    "NO_DATA": ErrorMapping(
        user_message="Не найдено статей по запросу",
        tech_message="Retrieval returned 0 documents for query",
        retryable=True
    ),
    "INSUFFICIENT_DATA": ErrorMapping(
        user_message="Недостаточно данных для анализа",
        tech_message="Retrieved documents below minimum threshold for analysis",
        retryable=True
    ),
    "EMPTY_QUERY": ErrorMapping(
        user_message="Запрос не может быть пустым",
        tech_message="Query string is empty or null",
        retryable=False
    ),

    # Budget & Limits
    "BUDGET_EXCEEDED": ErrorMapping(
        user_message="Превышен лимит обработки запроса",
        tech_message="Budget limit exceeded: max_tokens or cost threshold reached",
        retryable=False
    ),
    "TIMEOUT": ErrorMapping(
        user_message="Превышено время ожидания ответа",
        tech_message="Request timeout: model response took too long",
        retryable=True
    ),
    "RATE_LIMIT": ErrorMapping(
        user_message="Слишком много запросов, попробуйте через минуту",
        tech_message="Rate limit exceeded for user or global quota",
        retryable=True
    ),

    # Model Errors
    "MODEL_UNAVAILABLE": ErrorMapping(
        user_message="Сервис анализа временно недоступен",
        tech_message="Primary model unavailable, fallback failed or exhausted",
        retryable=True
    ),
    "MODEL_ERROR": ErrorMapping(
        user_message="Ошибка при генерации ответа",
        tech_message="Model returned error response or invalid format",
        retryable=True
    ),
    "API_KEY_INVALID": ErrorMapping(
        user_message="Ошибка конфигурации сервиса",
        tech_message="API key invalid or expired for model provider",
        retryable=False
    ),

    # Internal Errors
    "INTERNAL": ErrorMapping(
        user_message="Внутренняя ошибка сервиса",
        tech_message="Unhandled internal exception",
        retryable=True
    ),
    "ORCHESTRATOR_ERROR": ErrorMapping(
        user_message="Ошибка координации запроса",
        tech_message="Orchestrator pipeline failed at node",
        retryable=True
    ),
    "AGENT_ERROR": ErrorMapping(
        user_message="Ошибка модуля анализа",
        tech_message="Agent execution failed or returned invalid output",
        retryable=True
    ),

    # Configuration Errors
    "INVALID_COMMAND": ErrorMapping(
        user_message="Неизвестная команда",
        tech_message="Command not recognized by orchestrator",
        retryable=False
    ),
    "INVALID_PARAMS": ErrorMapping(
        user_message="Некорректные параметры запроса",
        tech_message="Request parameters failed validation",
        retryable=False
    ),
    "FEATURE_DISABLED": ErrorMapping(
        user_message="Функция временно отключена",
        tech_message="Feature flag disabled for this command",
        retryable=False
    ),
}


def get_error_mapping(code: str) -> ErrorMapping:
    """Get error mapping for code, or return generic INTERNAL error"""
    return ERROR_MAPPINGS.get(
        code,
        ErrorMapping(
            user_message="Неизвестная ошибка",
            tech_message=f"Unknown error code: {code}",
            retryable=True
        )
    )


def format_user_error(code: str, context: str = "") -> str:
    """Format user-friendly error message with optional context"""
    mapping = get_error_mapping(code)
    base_msg = mapping.user_message

    if context:
        return f"{base_msg}: {context}"
    return base_msg


def format_tech_error(code: str, details: str = "") -> str:
    """Format technical error message for logs"""
    mapping = get_error_mapping(code)
    base_msg = mapping.tech_message

    if details:
        return f"{base_msg} | Details: {details}"
    return base_msg


def is_retryable(code: str) -> bool:
    """Check if error code indicates retryable failure"""
    mapping = get_error_mapping(code)
    return mapping.retryable


# Common error scenarios with suggested actions
ERROR_ACTIONS: Dict[str, str] = {
    "NO_DATA": "Попробуйте изменить временной диапазон или расширить запрос",
    "BUDGET_EXCEEDED": "Уменьшите количество источников или сократите запрос",
    "TIMEOUT": "Попробуйте упростить запрос или уменьшить окно времени",
    "RATE_LIMIT": "Подождите несколько минут и попробуйте снова",
    "MODEL_UNAVAILABLE": "Попробуйте позже, сервис скоро восстановится",
}


def get_error_action(code: str) -> str:
    """Get suggested action for error code"""
    return ERROR_ACTIONS.get(code, "Попробуйте позже или обратитесь в поддержку")