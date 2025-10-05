#!/usr/bin/env python3
"""
Полный анализ и тестирование всех команд Telegram бота
Проверяет: запрос → обработка → база данных → ответ
"""
import asyncio
import os
import sys
from typing import Dict, Any, List
from datetime import datetime

# Импорты для тестирования
sys.path.insert(0, os.path.dirname(__file__))

async def analyze_command(command_name: str, test_query: str = None):
    """Полный анализ команды с трассировкой"""
    print(f"\n{'='*100}")
    print(f"АНАЛИЗ КОМАНДЫ: /{command_name}")
    print(f"{'='*100}")

    if test_query:
        print(f"Тестовый запрос: {test_query}")

    # Импортируем необходимые модули
    results = {
        'command': command_name,
        'query': test_query,
        'steps': [],
        'db_tables': [],
        'db_columns': [],
        'errors': [],
        'success': False
    }

    try:
        # Шаг 1: Определяем обработчик команды
        print(f"\n📍 ШАГ 1: Поиск обработчика команды")
        print(f"   Файл: bot_service/advanced_bot.py")

        handler_name = f"handle_{command_name}_command"
        print(f"   Метод: {handler_name}()")
        results['steps'].append(f"Handler: {handler_name}")

        # Шаг 2: Анализируем код обработчика
        print(f"\n📍 ШАГ 2: Анализ обработчика")

        import subprocess

        # Ищем строку с определением метода
        cmd = f'grep -n "async def {handler_name}" bot_service/advanced_bot.py'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.stdout:
            line_num = result.stdout.split(':')[0]
            print(f"   Найден в строке: {line_num}")

            # Читаем код обработчика
            cmd = f'sed -n "{line_num},+50p" bot_service/advanced_bot.py'
            code_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            code = code_result.stdout
            results['steps'].append(f"Code location: line {line_num}")

            # Анализируем вызовы
            if 'execute_' in code:
                # Ищем вызовы execute_*
                import re
                execute_calls = re.findall(r'execute_(\w+)', code)
                if execute_calls:
                    print(f"   Вызовы orchestrator:")
                    for call in set(execute_calls):
                        print(f"      → execute_{call}()")
                        results['steps'].append(f"Orchestrator: execute_{call}")

            if 'RankingAPI' in code or 'ranking_api' in code:
                print(f"   Прямой вызов: RankingAPI")
                results['steps'].append("Direct: RankingAPI")

            if 'ProductionDBClient' in code or 'db_client' in code:
                print(f"   Прямой вызов: ProductionDBClient")
                results['steps'].append("Direct: ProductionDBClient")

        else:
            print(f"   ❌ Обработчик не найден")
            results['errors'].append(f"Handler {handler_name} not found")
            return results

        # Шаг 3: Определяем таблицы БД
        print(f"\n📍 ШАГ 3: Определение таблиц БД")

        # Список известных таблиц для каждой команды
        table_mappings = {
            'search': ['article_chunks', 'articles'],
            'trends': ['article_chunks', 'articles'],
            'analyze': ['article_chunks', 'articles'],
            'ask': ['article_chunks', 'articles'],
            'summarize': ['articles', 'article_chunks'],
            'aggregate': ['articles'],
            'filter': ['articles'],
            'insights': ['articles', 'article_chunks'],
            'sentiment': ['articles', 'article_chunks'],
            'topics': ['articles', 'article_chunks'],
            'gpt': ['articles', 'article_chunks'],
        }

        tables = table_mappings.get(command_name, ['unknown'])
        results['db_tables'] = tables

        print(f"   Таблицы: {', '.join(tables)}")

        # Шаг 4: Проверяем данные в таблицах
        print(f"\n📍 ШАГ 4: Проверка данных в БД")

        from database.production_db_client import ProductionDBClient
        pg_dsn = os.getenv("PG_DSN") or os.getenv("DATABASE_URL")

        if not pg_dsn:
            print(f"   ⚠️  PG_DSN не установлен, используем Railway")
            # Попробуем через Railway
            check_cmd = f'railway run python -c "import os; print(os.getenv(\\"DATABASE_URL\\"))"'
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.stdout and result.stdout.strip():
                pg_dsn = result.stdout.strip()

        if pg_dsn:
            db = ProductionDBClient(pg_dsn)

            for table in tables:
                if table == 'unknown':
                    continue

                try:
                    # Проверяем количество записей
                    with db._cursor() as cur:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cur.fetchone()[0]
                        print(f"   ✅ {table}: {count:,} записей")

                        # Проверяем ключевые столбцы
                        if table == 'article_chunks':
                            cur.execute("""
                                SELECT
                                    COUNT(*) FILTER (WHERE embedding_vector IS NOT NULL) as with_vector,
                                    COUNT(*) FILTER (WHERE text_search_vector IS NOT NULL) as with_fts
                                FROM article_chunks
                                WHERE published_at >= NOW() - INTERVAL '24 hours'
                            """)
                            row = cur.fetchone()
                            print(f"      - embedding_vector (24ч): {row[0]:,}")
                            print(f"      - text_search_vector (24ч): {row[1]:,}")
                            results['db_columns'].extend(['embedding_vector', 'text_search_vector'])

                        elif table == 'articles':
                            cur.execute("""
                                SELECT
                                    COUNT(*) FILTER (WHERE content IS NOT NULL) as with_content,
                                    COUNT(*) FILTER (WHERE clean_text IS NOT NULL) as with_clean
                                FROM articles
                                WHERE published_at >= NOW() - INTERVAL '24 hours'
                            """)
                            row = cur.fetchone()
                            print(f"      - content (24ч): {row[0]:,}")
                            print(f"      - clean_text (24ч): {row[1]:,}")
                            results['db_columns'].extend(['content', 'clean_text'])

                except Exception as e:
                    print(f"   ❌ Ошибка проверки {table}: {e}")
                    results['errors'].append(f"DB check failed: {table}: {e}")

        else:
            print(f"   ⚠️  Невозможно подключиться к БД")
            results['errors'].append("No database connection")

        # Шаг 5: Тестовый запрос (если возможно)
        print(f"\n📍 ШАГ 5: Тестовый запрос")

        if test_query and command_name in ['search', 'analyze', 'trends']:
            print(f"   Выполняю: /{command_name} {test_query}")

            try:
                if command_name == 'search':
                    from ranking_api import RankingAPI
                    from schemas.ranking_schemas import SearchRequest

                    api = RankingAPI()
                    request = SearchRequest(
                        query=test_query,
                        method='hybrid',
                        limit=3,
                        explain=True
                    )

                    response = await api.search(request)
                    print(f"   ✅ Получено результатов: {len(response.results)}")

                    if response.results:
                        print(f"   Первый результат:")
                        first = response.results[0]
                        print(f"      - {first.get('title_norm', 'No title')[:80]}")
                        print(f"      - Scores: {first.get('scores', {})}")

                    results['success'] = True

                elif command_name == 'analyze':
                    from services.orchestrator import execute_analyze_command

                    payload = await execute_analyze_command(
                        mode='keywords',
                        query=test_query,
                        window='24h'
                    )

                    print(f"   ✅ Ответ получен")
                    if 'text' in payload:
                        preview = payload['text'][:200] if len(payload['text']) > 200 else payload['text']
                        print(f"   Превью: {preview}...")

                    results['success'] = True

                elif command_name == 'trends':
                    from services.orchestrator import execute_trends_command

                    payload = await execute_trends_command(
                        window='24h',
                        k_final=3
                    )

                    print(f"   ✅ Ответ получен")
                    if 'text' in payload:
                        preview = payload['text'][:200] if len(payload['text']) > 200 else payload['text']
                        print(f"   Превью: {preview}...")

                    results['success'] = True

            except Exception as e:
                print(f"   ❌ Ошибка теста: {e}")
                results['errors'].append(f"Test failed: {e}")
                import traceback
                traceback.print_exc()

        else:
            print(f"   ⏭️  Тест пропущен (нет test_query или команда не поддерживается)")

        # Шаг 6: Путь данных
        print(f"\n📍 ШАГ 6: Полный путь данных")
        print(f"   1️⃣  Telegram Bot → advanced_bot.py::{handler_name}()")

        if results['steps']:
            for i, step in enumerate(results['steps'], 2):
                print(f"   {i}️⃣  {step}")

        if results['db_tables']:
            print(f"   🗄️  База данных: {', '.join(results['db_tables'])}")

        if results['db_columns']:
            print(f"   📊 Столбцы: {', '.join(set(results['db_columns']))}")

        print(f"   🔙 Ответ → Telegram Bot → Пользователь")

    except Exception as e:
        print(f"\n❌ Критическая ошибка анализа: {e}")
        results['errors'].append(f"Critical: {e}")
        import traceback
        traceback.print_exc()

    return results

async def main():
    print("="*100)
    print("ПОЛНЫЙ АНАЛИЗ ВСЕХ КОМАНД TELEGRAM БОТА")
    print("="*100)
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Список команд для анализа
    commands_to_test = [
        ('search', 'AI technology'),
        ('trends', None),
        ('analyze', 'artificial intelligence'),
        ('ask', 'What is happening with AI?'),
        ('summarize', 'latest AI news'),
        ('aggregate', None),
        ('filter', None),
        ('insights', 'AI trends'),
        ('sentiment', 'AI regulation'),
        ('topics', None),
        ('gpt', 'explain quantum computing'),
    ]

    all_results = []

    for command, query in commands_to_test:
        try:
            result = await analyze_command(command, query)
            all_results.append(result)

            # Пауза между тестами
            await asyncio.sleep(1)

        except Exception as e:
            print(f"\n❌ Ошибка анализа {command}: {e}")
            all_results.append({
                'command': command,
                'query': query,
                'errors': [str(e)],
                'success': False
            })

    # Итоговая таблица
    print(f"\n{'='*100}")
    print("ИТОГОВАЯ ТАБЛИЦА")
    print(f"{'='*100}\n")

    print(f"{'Команда':<15} {'Таблицы БД':<40} {'Статус':<15} {'Ошибки':<30}")
    print("-"*100)

    for result in all_results:
        cmd = result['command']
        tables = ', '.join(result.get('db_tables', ['unknown']))
        status = '✅ OK' if result.get('success') else '⚠️  Needs Check'
        errors = '; '.join(result.get('errors', [])[:2]) if result.get('errors') else '-'

        print(f"{cmd:<15} {tables:<40} {status:<15} {errors:<30}")

    # Статистика
    print(f"\n{'='*100}")
    print("СТАТИСТИКА")
    print(f"{'='*100}\n")

    total = len(all_results)
    success = len([r for r in all_results if r.get('success')])
    with_errors = len([r for r in all_results if r.get('errors')])

    print(f"📊 Всего команд: {total}")
    print(f"✅ Успешных тестов: {success}")
    print(f"⚠️  С предупреждениями: {with_errors}")
    print(f"📈 Процент успеха: {success/total*100:.1f}%")

    # Сохраняем отчет
    report_file = 'COMMAND_ANALYSIS_REPORT.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# Полный анализ команд Telegram бота\n\n")
        f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Статистика\n\n")
        f.write(f"- Всего команд: {total}\n")
        f.write(f"- Успешных тестов: {success}\n")
        f.write(f"- С ошибками: {with_errors}\n\n")
        f.write(f"## Детали\n\n")

        for result in all_results:
            f.write(f"### /{result['command']}\n\n")
            f.write(f"**Тестовый запрос:** {result.get('query', 'N/A')}\n\n")
            f.write(f"**Таблицы БД:** {', '.join(result.get('db_tables', ['unknown']))}\n\n")
            f.write(f"**Столбцы:** {', '.join(set(result.get('db_columns', ['unknown'])))}\n\n")

            if result.get('steps'):
                f.write(f"**Шаги обработки:**\n")
                for step in result['steps']:
                    f.write(f"- {step}\n")
                f.write("\n")

            if result.get('errors'):
                f.write(f"**Ошибки:**\n")
                for error in result['errors']:
                    f.write(f"- ❌ {error}\n")
                f.write("\n")

            f.write(f"**Статус:** {'✅ OK' if result.get('success') else '⚠️ Needs Check'}\n\n")
            f.write("---\n\n")

    print(f"\n📄 Отчет сохранен: {report_file}")

if __name__ == "__main__":
    asyncio.run(main())
