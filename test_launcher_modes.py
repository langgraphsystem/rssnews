#!/usr/bin/env python3
"""
Тестирование всех режимов launcher.py
"""
import os
import sys
import subprocess

# Добавляем текущую директорию в PATH для импорта
sys.path.insert(0, os.path.dirname(__file__))

from launcher import build_command

def test_mode(mode_name, env_vars=None):
    """Test a specific SERVICE_MODE"""
    print(f"\n{'='*80}")
    print(f"Тестирую режим: {mode_name}")
    print(f"{'='*80}")

    # Устанавливаем переменные окружения
    if env_vars:
        for key, value in env_vars.items():
            os.environ[key] = str(value)

    os.environ['SERVICE_MODE'] = mode_name

    try:
        cmd = build_command()
        print(f"✅ Команда: {cmd}")
        return True
    except SystemExit as e:
        print(f"❌ Ошибка: код выхода {e.code}")
        return False
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False
    finally:
        # Очищаем переменные
        if env_vars:
            for key in env_vars.keys():
                os.environ.pop(key, None)

def main():
    print("="*80)
    print("ТЕСТИРОВАНИЕ ВСЕХ РЕЖИМОВ launcher.py")
    print("="*80)

    # Определяем все режимы для тестирования
    test_cases = [
        ("poll", {"POLL_WORKERS": "10", "POLL_BATCH": "10"}),
        ("work", {"WORK_WORKERS": "10", "WORK_BATCH": "50"}),
        ("work", {"WORK_WORKERS": "10", "WORK_BATCH": "50", "WORK_SIMPLIFIED": "true"}),
        ("work-continuous", {"WORK_CONTINUOUS_INTERVAL": "30", "WORK_CONTINUOUS_BATCH": "50"}),
        ("embedding", {"EMBEDDING_BATCH": "1000"}),
        ("chunking", {"CHUNKING_BATCH": "100"}),
        ("chunk-continuous", {"CHUNK_CONTINUOUS_INTERVAL": "30", "CHUNK_CONTINUOUS_BATCH": "100"}),
        ("fts", {"FTS_BATCH": "100000"}),
        ("fts-continuous", {"FTS_CONTINUOUS_INTERVAL": "60"}),
        ("openai-migration", {"MIGRATION_INTERVAL": "60", "MIGRATION_BATCH": "100"}),
        ("bot", {}),
        ("invalid-mode", {}),  # Должен провалиться
    ]

    results = []

    for mode, env_vars in test_cases:
        success = test_mode(mode, env_vars)
        results.append((mode, success))

    # Итоговая таблица
    print("\n" + "="*80)
    print("ИТОГОВАЯ ТАБЛИЦА")
    print("="*80)
    print()
    print(f"{'Режим':<25} {'Статус':<10} {'Ожидается':<15}")
    print("-"*80)

    for mode, success in results:
        expected = "fail" if mode == "invalid-mode" else "success"
        actual = "success" if success else "fail"
        status = "✅" if (actual == expected) else "❌"

        print(f"{mode:<25} {status} {actual:<10} {expected:<15}")

    # Проверка соответствия документации
    print("\n" + "="*80)
    print("ПРОВЕРКА СООТВЕТСТВИЯ ДОКУМЕНТАЦИИ")
    print("="*80)

    documented_modes = [
        "poll", "work", "work-continuous", "embedding",
        "chunking", "chunk-continuous", "openai-migration", "bot"
    ]

    # Новые режимы FTS
    new_fts_modes = ["fts", "fts-continuous"]

    print("\n📋 Документированные режимы:")
    for mode in documented_modes:
        found = any(r[0] == mode and r[1] for r in results)
        status = "✅" if found else "❌"
        print(f"  {status} {mode}")

    print("\n🆕 Новые FTS режимы:")
    for mode in new_fts_modes:
        found = any(r[0] == mode and r[1] for r in results)
        status = "✅" if found else "❌"
        print(f"  {status} {mode}")

    # Проверяем команды для FTS
    print("\n" + "="*80)
    print("ДЕТАЛЬНАЯ ПРОВЕРКА FTS РЕЖИМОВ")
    print("="*80)

    print("\n🔍 FTS режим (one-off):")
    os.environ['SERVICE_MODE'] = 'fts'
    os.environ['FTS_BATCH'] = '50000'
    cmd = build_command()
    print(f"  Команда: {cmd}")
    expected_fts = "python main.py services run-once --services fts --fts-batch 50000"
    if cmd == expected_fts:
        print(f"  ✅ Команда корректна")
    else:
        print(f"  ❌ Ожидалось: {expected_fts}")

    print("\n🔍 FTS-continuous режим:")
    os.environ['SERVICE_MODE'] = 'fts-continuous'
    os.environ['FTS_CONTINUOUS_INTERVAL'] = '120'
    cmd = build_command()
    print(f"  Команда: {cmd}")
    expected_fts_cont = "python main.py services start --services fts --fts-interval 120"
    if cmd == expected_fts_cont:
        print(f"  ✅ Команда корректна")
    else:
        print(f"  ❌ Ожидалось: {expected_fts_cont}")

    # Рекомендации для Railway
    print("\n" + "="*80)
    print("РЕКОМЕНДАЦИИ ДЛЯ RAILWAY")
    print("="*80)

    print("\n📝 Для нового FTS сервиса (RSS FTS) установить:")
    print()
    print("  Переменные окружения:")
    print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SERVICE_MODE=fts-continuous")
    print("  RAILWAY_SERVICE_ID=ffe65f79-4dc5-4757-b772-5a99c7ea624f")
    print("  FTS_BATCH=100000")
    print("  FTS_CONTINUOUS_INTERVAL=60")
    print()
    print("  Команда запуска:")
    print("  python launcher.py")
    print()
    print("  Результат:")
    print("  → python main.py services start --services fts --fts-interval 60")

    # Проверка всех сервисов
    print("\n" + "="*80)
    print("КОНФИГУРАЦИЯ ВСЕХ RAILWAY СЕРВИСОВ")
    print("="*80)

    services_config = [
        ("RSS POLL", "poll", "POLL_WORKERS=10, POLL_BATCH=10"),
        ("WORK", "work-continuous", "WORK_CONTINUOUS_INTERVAL=30, WORK_CONTINUOUS_BATCH=50"),
        ("OpenAIEmbending", "embedding", "EMBEDDING_BATCH=1000"),
        ("CHUNK", "chunk-continuous", "CHUNK_CONTINUOUS_INTERVAL=30, CHUNK_CONTINUOUS_BATCH=100"),
        ("RSS FTS", "fts-continuous", "FTS_BATCH=100000, FTS_CONTINUOUS_INTERVAL=60"),
        ("Bot", "bot", ""),
        ("rssnews", "openai-migration", "MIGRATION_INTERVAL=60, MIGRATION_BATCH=100"),
    ]

    print()
    print(f"{'Сервис':<20} {'SERVICE_MODE':<20} {'Дополнительные переменные':<50}")
    print("-"*80)

    for service, mode, vars in services_config:
        # Проверяем, что режим работает
        mode_works = any(r[0] == mode and r[1] for r in results)
        status = "✅" if mode_works else "❌"
        print(f"{status} {service:<18} {mode:<20} {vars:<50}")

    print("\n" + "="*80)
    print("ИТОГ")
    print("="*80)

    total_modes = len([r for r in results if r[0] != "invalid-mode"])
    working_modes = len([r for r in results if r[0] != "invalid-mode" and r[1]])

    print(f"\n✅ Рабочих режимов: {working_modes}/{total_modes}")

    if working_modes == total_modes:
        print("🎉 Все режимы работают корректно!")
        print("\n📌 launcher.py готов к деплою на Railway")
        return 0
    else:
        print("⚠️  Есть проблемы с некоторыми режимами")
        return 1

if __name__ == "__main__":
    sys.exit(main())
