#!/usr/bin/env python3
"""
Проверка Railway сервиса по ID
Определяет назначение сервиса c015bdb5-710d-46b8-ad86-c566b99e7560
"""
import subprocess
import json

def check_service(service_id):
    print("="*80)
    print(f"ПРОВЕРКА RAILWAY СЕРВИСА: {service_id}")
    print("="*80)

    # Известные сервисы из кодовой базы
    known_services = {
        "ffe65f79-4dc5-4757-b772-5a99c7ea624f": {
            "name": "RSS FTS",
            "mode": "fts-continuous",
            "description": "Full-Text Search индексация"
        },
        "c015bdb5-710d-46b8-ad86-c566b99e7560": {
            "name": "Unknown - нужно проверить",
            "mode": "unknown",
            "description": "Сервис не документирован"
        }
    }

    # Проверяем в известных
    if service_id in known_services:
        info = known_services[service_id]
        print(f"\n📋 Информация из кодовой базы:")
        print(f"   Название: {info['name']}")
        print(f"   SERVICE_MODE: {info['mode']}")
        print(f"   Описание: {info['description']}")
    else:
        print(f"\n⚠️  Сервис не найден в документации")

    # Попробуем получить информацию через Railway CLI
    print(f"\n🔍 Попытка получить информацию через Railway CLI...")

    try:
        # Пробуем разные команды
        commands = [
            f"railway vars --service-id {service_id}",
            f"railway logs --service-id {service_id} --limit 10",
            "railway service",
        ]

        for cmd in commands:
            print(f"\n   Выполняю: {cmd}")
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=20
                )

                if result.returncode == 0 and result.stdout:
                    print(f"   ✅ Успешно:")
                    print(result.stdout[:500])
                    break
                elif result.stderr:
                    print(f"   ❌ Ошибка: {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                print(f"   ⏱️  Timeout")
                continue
            except Exception as e:
                print(f"   ❌ Исключение: {e}")
                continue

    except Exception as e:
        print(f"\n❌ Не удалось получить информацию: {e}")

    # Ищем упоминания в коде
    print(f"\n🔎 Поиск в кодовой базе...")

    try:
        result = subprocess.run(
            f'grep -r "{service_id}" . --include="*.py" --include="*.md" --include="*.txt" 2>/dev/null',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.stdout:
            matches = result.stdout.split('\n')[:10]
            print(f"   Найдено {len(matches)} упоминаний:")
            for match in matches:
                if match.strip():
                    print(f"   {match[:120]}")
        else:
            print(f"   ⚠️  Упоминаний не найдено в коде")

    except Exception as e:
        print(f"   ❌ Ошибка поиска: {e}")

    # Проверяем в update_railway_vars.py
    print(f"\n📝 Проверка в update_railway_vars.py...")
    try:
        with open('update_railway_vars.py', 'r', encoding='utf-8') as f:
            content = f.read()
            if service_id in content:
                print(f"   ✅ Найден в update_railway_vars.py")
                # Находим контекст
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if service_id in line:
                        context = '\n'.join(lines[max(0, i-3):min(len(lines), i+4)])
                        print(f"\n   Контекст:\n{context}")
            else:
                print(f"   ⚠️  Не найден в update_railway_vars.py")
    except Exception as e:
        print(f"   ❌ Ошибка чтения: {e}")

    # Проверяем в check_railway_*.py файлах
    print(f"\n🔍 Проверка в check_railway_*.py...")
    import glob
    for file in glob.glob('check_railway*.py'):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                if service_id in f.read():
                    print(f"   ✅ Найден в {file}")
        except:
            pass

    # Итоговое заключение
    print(f"\n{'='*80}")
    print("ИТОГОВОЕ ЗАКЛЮЧЕНИЕ")
    print(f"{'='*80}")

    print(f"\n🆔 Service ID: {service_id}")

    # Анализируем на основе паттернов
    if service_id == "c015bdb5-710d-46b8-ad86-c566b99e7560":
        print(f"\n❓ Сервис не документирован в основных конфигурационных файлах")
        print(f"\n📌 Возможные варианты:")
        print(f"   1. Старый/устаревший сервис (не используется)")
        print(f"   2. Тестовый сервис")
        print(f"   3. Резервный сервис")
        print(f"   4. Сервис с другим проектом")
        print(f"\n💡 Рекомендация: Проверить через Railway Dashboard")
        print(f"   railway.app → Project → Services")

if __name__ == "__main__":
    service_id = "c015bdb5-710d-46b8-ad86-c566b99e7560"
    check_service(service_id)
