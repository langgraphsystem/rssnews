#!/usr/bin/env python3
"""
Проверка конфигурации Railway сервисов
Проверяет SERVICE_MODE и RAILWAY_SERVICE_ID для каждого сервиса
"""
import os
import subprocess
import json

def run_command(cmd):
    """Execute shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def get_services():
    """Get list of Railway services"""
    # Используем railway CLI для получения списка сервисов
    output = run_command("railway service list --json 2>/dev/null || railway service 2>&1")

    # Известные сервисы из вывода
    known_services = [
        "WORK",
        "OpenAIEmbending",
        "RSS POLL",
        "Bot",
        "rssnews",
        "CHUNK",
        "RSS FTS"
    ]

    return known_services

def get_service_vars(service_name):
    """Get environment variables for a specific service"""
    cmd = f'railway vars --service "{service_name}" --json 2>/dev/null'
    output = run_command(cmd)

    if output.startswith("Error") or not output:
        # Fallback to text output
        cmd = f'railway vars --service "{service_name}" 2>/dev/null'
        output = run_command(cmd)

        # Parse text output
        vars_dict = {}
        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                vars_dict[key.strip()] = value.strip()
        return vars_dict

    try:
        return json.loads(output)
    except:
        return {}

def main():
    print("=" * 80)
    print("ПРОВЕРКА RAILWAY СЕРВИСОВ")
    print("=" * 80)

    services = get_services()

    print(f"\n📋 Найдено сервисов: {len(services)}\n")

    # Маппинг ожидаемых SERVICE_MODE для каждого сервиса
    expected_modes = {
        "WORK": "work-continuous",
        "OpenAIEmbending": "embedding",
        "RSS POLL": "poll",
        "Bot": "bot",
        "rssnews": "openai-migration",  # основной сервис
        "CHUNK": "chunk-continuous",
        "RSS FTS": "fts-continuous"  # НОВЫЙ FTS сервис
    }

    # Проверка каждого сервиса
    results = []

    for service in services:
        print(f"🔍 Проверяю сервис: {service}")
        print("-" * 80)

        vars_dict = get_service_vars(service)

        service_mode = vars_dict.get('SERVICE_MODE', '❌ НЕ УСТАНОВЛЕН')
        service_id = vars_dict.get('RAILWAY_SERVICE_ID', vars_dict.get('SERVICE_ID', '❌ НЕ УСТАНОВЛЕН'))

        expected_mode = expected_modes.get(service, '⚠️  Неизвестный сервис')

        # Проверка корректности
        mode_ok = service_mode == expected_mode
        mode_status = "✅" if mode_ok else "❌"

        print(f"  SERVICE_MODE:        {mode_status} {service_mode}")
        print(f"  Ожидается:           {expected_mode}")
        print(f"  RAILWAY_SERVICE_ID:  {service_id}")

        # Специальная проверка для FTS
        if service == "RSS FTS":
            expected_fts_id = "ffe65f79-4dc5-4757-b772-5a99c7ea624f"
            fts_id_ok = service_id == expected_fts_id
            fts_status = "✅" if fts_id_ok else "❌"
            print(f"  FTS ID корректен:    {fts_status} (ожидается: {expected_fts_id})")

            # Проверка FTS переменных
            fts_batch = vars_dict.get('FTS_BATCH', 'не установлен')
            fts_interval = vars_dict.get('FTS_CONTINUOUS_INTERVAL', 'не установлен')
            print(f"  FTS_BATCH:           {fts_batch}")
            print(f"  FTS_CONTINUOUS_INTERVAL: {fts_interval}")

        print()

        results.append({
            'service': service,
            'mode': service_mode,
            'expected': expected_mode,
            'ok': mode_ok,
            'service_id': service_id
        })

    # Итоговая таблица
    print("=" * 80)
    print("ИТОГОВАЯ ТАБЛИЦА")
    print("=" * 80)
    print()
    print(f"{'Сервис':<20} {'SERVICE_MODE':<20} {'Ожидается':<20} {'Статус':<10}")
    print("-" * 80)

    for r in results:
        status = "✅ OK" if r['ok'] else "❌ ОШИБКА"
        print(f"{r['service']:<20} {r['mode']:<20} {r['expected']:<20} {status:<10}")

    # Проверка launcher.py
    print("\n" + "=" * 80)
    print("ПРОВЕРКА launcher.py")
    print("=" * 80)

    if os.path.exists('launcher.py'):
        with open('launcher.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем поддержку всех режимов
        supported_modes = []
        for mode in expected_modes.values():
            if f'mode == "{mode}"' in content or f"mode == '{mode}'" in content:
                supported_modes.append(mode)

        print(f"\n✅ Поддерживаемые режимы в launcher.py:")
        for mode in set(supported_modes):
            print(f"   - {mode}")

        missing_modes = set(expected_modes.values()) - set(supported_modes)
        if missing_modes:
            print(f"\n❌ Отсутствующие режимы:")
            for mode in missing_modes:
                print(f"   - {mode}")

        # Проверяем проблемы с отступами
        print(f"\n🔍 Проверка отступов...")
        lines = content.split('\n')
        indent_issues = []

        for i, line in enumerate(lines, 1):
            # Проверяем смешивание табов и пробелов
            if '\t' in line and '    ' in line[:len(line) - len(line.lstrip())]:
                indent_issues.append(f"Строка {i}: смешивание табов и пробелов")

            # Проверяем некорректные отступы для if/def
            if line.strip().startswith(('if ', 'def ', 'return ')) and not line.startswith(('    ', '\t', 'if ', 'def ', 'return ')):
                if line[0] == ' ':
                    indent_issues.append(f"Строка {i}: некорректный отступ для '{line.strip()[:20]}...'")

        if indent_issues:
            print(f"❌ Найдены проблемы с отступами:")
            for issue in indent_issues[:10]:  # Показываем первые 10
                print(f"   {issue}")
        else:
            print(f"✅ Проблем с отступами не найдено")

    print("\n" + "=" * 80)
    print("РЕКОМЕНДАЦИИ")
    print("=" * 80)

    # Генерируем рекомендации
    recs = []

    for r in results:
        if not r['ok']:
            recs.append(f"Установить SERVICE_MODE={r['expected']} для сервиса '{r['service']}'")

    if recs:
        print("\n⚠️  Необходимые исправления:\n")
        for i, rec in enumerate(recs, 1):
            print(f"{i}. {rec}")
    else:
        print("\n✅ Все сервисы настроены корректно!")

if __name__ == "__main__":
    main()
