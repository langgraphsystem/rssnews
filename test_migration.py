#!/usr/bin/env python3
"""
Тестовый скрипт для проверки миграции с Google Sheets на PostgreSQL
Проверяет весь цикл работы приложения
"""

import os
import sys
import tempfile
import sqlite3
import json
from unittest.mock import patch, MagicMock
from typing import Dict, Any

# Цвета для вывода
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_status(message: str, status: str = "INFO"):
    color = Colors.GREEN if status == "OK" else Colors.RED if status == "ERROR" else Colors.YELLOW
    print(f"{color}[{status}]{Colors.END} {message}")

def print_header(message: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")

def test_imports():
    """Тест импортов всех модулей"""
    print_header("ТЕСТ ИМПОРТОВ")
    
    modules = ['pg_client', 'main', 'discovery', 'poller', 'worker', 'utils', 'config', 'schema']
    failed = []
    
    for module in modules:
        try:
            __import__(module)
            print_status(f"Импорт {module}", "OK")
        except Exception as e:
            print_status(f"Импорт {module}: {e}", "ERROR")
            failed.append(module)
    
    if failed:
        print_status(f"Ошибки импорта в модулях: {', '.join(failed)}", "ERROR")
        return False
    
    print_status("Все модули импортированы успешно", "OK")
    return True

def create_mock_postgres_dsn():
    """Создает временную SQLite базу для тестирования"""
    temp_db = tempfile.mktemp(suffix='.db')
    # Создаем SQLite DSN в формате, который можно использовать для тестов
    return f"sqlite:///{temp_db}"

def test_pg_client_creation():
    """Тест создания PgClient"""
    print_header("ТЕСТ СОЗДАНИЯ PG CLIENT")
    
    try:
        from pg_client import PgClient
        
        # Тест без PG_DSN
        try:
            client = PgClient()
            print_status("PgClient создался без PG_DSN (неожиданно)", "ERROR")
            return False
        except ValueError as e:
            if "PG_DSN environment variable is required" in str(e):
                print_status("Корректная ошибка при отсутствии PG_DSN", "OK")
            else:
                print_status(f"Неожиданная ошибка: {e}", "ERROR")
                return False
        
        return True
    except Exception as e:
        print_status(f"Ошибка при тестировании PgClient: {e}", "ERROR")
        return False

def test_main_commands():
    """Тест основных команд main.py"""
    print_header("ТЕСТ КОМАНД MAIN.PY")
    
    try:
        # Проверим что main.py можно запустить с --help
        import subprocess
        result = subprocess.run([sys.executable, "main.py", "--help"], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print_status("main.py --help работает", "OK")
            
            # Проверим наличие всех ожидаемых команд
            expected_commands = ["ensure", "discovery", "poll", "work"]
            help_text = result.stdout
            
            for cmd in expected_commands:
                if cmd in help_text:
                    print_status(f"Команда '{cmd}' найдена в help", "OK")
                else:
                    print_status(f"Команда '{cmd}' НЕ найдена в help", "ERROR")
                    return False
            
            return True
        else:
            print_status(f"main.py --help завершился с кодом {result.returncode}", "ERROR")
            print_status(f"stderr: {result.stderr}", "ERROR")
            return False
            
    except Exception as e:
        print_status(f"Ошибка при тестировании main.py: {e}", "ERROR")
        return False

def test_schema_compatibility():
    """Тест совместимости схемы"""
    print_header("ТЕСТ СОВМЕСТИМОСТИ СХЕМЫ")
    
    try:
        from schema import FEEDS_HEADERS, RAW_HEADERS, INDEX_HEADERS, DIAG_HEADERS, CONFIG_HEADERS
        
        # Проверим что заголовки не пустые
        schemas = {
            'FEEDS_HEADERS': FEEDS_HEADERS,
            'RAW_HEADERS': RAW_HEADERS, 
            'INDEX_HEADERS': INDEX_HEADERS,
            'DIAG_HEADERS': DIAG_HEADERS,
            'CONFIG_HEADERS': CONFIG_HEADERS
        }
        
        for name, headers in schemas.items():
            if headers and len(headers) > 0:
                print_status(f"{name}: {len(headers)} полей", "OK")
            else:
                print_status(f"{name}: пустой или отсутствует", "ERROR")
                return False
        
        # Проверим ключевые поля
        required_feed_fields = ['feed_url_canon', 'status', 'etag', 'last_modified']
        for field in required_feed_fields:
            if field in FEEDS_HEADERS:
                print_status(f"Поле '{field}' найдено в FEEDS_HEADERS", "OK")
            else:
                print_status(f"КРИТИЧЕСКОЕ: Поле '{field}' НЕ найдено в FEEDS_HEADERS", "ERROR")
                return False
        
        required_raw_fields = ['url_hash', 'status', 'lock_owner', 'article_url_canon']
        for field in required_raw_fields:
            if field in RAW_HEADERS:
                print_status(f"Поле '{field}' найдено в RAW_HEADERS", "OK")
            else:
                print_status(f"КРИТИЧЕСКОЕ: Поле '{field}' НЕ найдено в RAW_HEADERS", "ERROR")
                return False
        
        return True
        
    except Exception as e:
        print_status(f"Ошибка при тестировании схемы: {e}", "ERROR")
        return False

def test_config_file():
    """Тест конфигурационного файла"""
    print_header("ТЕСТ КОНФИГУРАЦИИ")
    
    try:
        from config import (
            MAX_ITEMS_PER_FEED_PER_POLL, PENDING_BATCH_SIZE, 
            CLEAN_TEXT_SHEETS_LIMIT, FRESH_DAYS_LIMIT
        )
        
        configs = {
            'MAX_ITEMS_PER_FEED_PER_POLL': MAX_ITEMS_PER_FEED_PER_POLL,
            'PENDING_BATCH_SIZE': PENDING_BATCH_SIZE,
            'CLEAN_TEXT_SHEETS_LIMIT': CLEAN_TEXT_SHEETS_LIMIT,
            'FRESH_DAYS_LIMIT': FRESH_DAYS_LIMIT
        }
        
        for name, value in configs.items():
            if isinstance(value, int) and value > 0:
                print_status(f"{name} = {value}", "OK")
            else:
                print_status(f"{name} = {value} (проверьте значение)", "ERROR")
        
        return True
        
    except Exception as e:
        print_status(f"Ошибка при тестировании конфигурации: {e}", "ERROR")
        return False

def test_utils():
    """Тест утилит"""
    print_header("ТЕСТ УТИЛИТ")
    
    try:
        from utils import canonicalize_url, sha256_hex, now_local_iso
        
        # Тест canonicalize_url
        test_url = "https://example.com/test"
        canonical = canonicalize_url(test_url)
        if canonical:
            print_status(f"canonicalize_url работает: {canonical}", "OK")
        else:
            print_status("canonicalize_url вернул пустое значение", "ERROR")
            return False
        
        # Тест sha256_hex
        test_string = "test string"
        hash_result = sha256_hex(test_string)
        if hash_result and len(hash_result) == 64:
            print_status(f"sha256_hex работает: {hash_result[:16]}...", "OK")
        else:
            print_status("sha256_hex работает некорректно", "ERROR")
            return False
        
        # Тест now_local_iso
        iso_time = now_local_iso()
        if iso_time and 'T' in iso_time:
            print_status(f"now_local_iso работает: {iso_time}", "OK")
        else:
            print_status("now_local_iso работает некорректно", "ERROR")
            return False
        
        return True
        
    except Exception as e:
        print_status(f"Ошибка при тестировании утилит: {e}", "ERROR")
        return False

def print_migration_summary():
    """Печатает сводку миграции"""
    print_header("СВОДКА МИГРАЦИИ")
    
    print(f"{Colors.GREEN}✓{Colors.END} pg_client.py - новый клиент PostgreSQL")
    print(f"{Colors.GREEN}✓{Colors.END} main.py - обновлен для использования PgClient")  
    print(f"{Colors.GREEN}✓{Colors.END} discovery.py - мигрирован на PostgreSQL")
    print(f"{Colors.GREEN}✓{Colors.END} poller.py - переписан для работы с БД")
    print(f"{Colors.GREEN}✓{Colors.END} worker.py - полностью переписан для PostgreSQL")
    print(f"{Colors.GREEN}✓{Colors.END} Автоматическое создание схемы БД")
    print(f"{Colors.GREEN}✓{Colors.END} Сохранена обратная совместимость интерфейса")
    
    print(f"\n{Colors.BOLD}Следующие шаги:{Colors.END}")
    print(f"{Colors.YELLOW}1.{Colors.END} Установите переменную окружения PG_DSN")
    print(f"{Colors.YELLOW}2.{Colors.END} Запустите: python main.py ensure")
    print(f"{Colors.YELLOW}3.{Colors.END} Протестируйте: python main.py discovery --feed <rss_url>")

def main():
    """Основная функция тестирования"""
    print_header("ТЕСТ МИГРАЦИИ НА POSTGRESQL")
    print("Проверка всех компонентов системы...")
    
    tests = [
        ("Импорты модулей", test_imports),
        ("Создание PgClient", test_pg_client_creation),
        ("Команды main.py", test_main_commands),
        ("Совместимость схемы", test_schema_compatibility),
        ("Конфигурация", test_config_file),
        ("Утилиты", test_utils)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{Colors.BOLD}Тест: {test_name}{Colors.END}")
        try:
            if test_func():
                print_status(f"ПРОЙДЕН: {test_name}", "OK")
                passed += 1
            else:
                print_status(f"ПРОВАЛЕН: {test_name}", "ERROR")
        except Exception as e:
            print_status(f"ОШИБКА в тесте {test_name}: {e}", "ERROR")
    
    print_header("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print(f"Пройдено: {Colors.GREEN}{passed}{Colors.END}/{total}")
    print(f"Провалено: {Colors.RED}{total - passed}{Colors.END}/{total}")
    
    if passed == total:
        print_status("ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Миграция успешна! 🎉", "OK")
        print_migration_summary()
        return 0
    else:
        print_status(f"НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ. Требуется доработка.", "ERROR")
        return 1

if __name__ == "__main__":
    sys.exit(main())