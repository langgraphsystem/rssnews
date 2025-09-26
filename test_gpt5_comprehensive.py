#!/usr/bin/env python3
"""
Comprehensive GPT-5 Testing Suite (2025)
Tests all GPT-5 models, parameters, and functionalities
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gpt5_comprehensive_test.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class GPT5ComprehensiveTester:
    """Comprehensive tester for all GPT-5 models and parameters"""

    def __init__(self):
        """Initialize with Railway environment variables"""
        # Ensure we have the API key from Railway
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set! Required for GPT-5 testing.")

        logger.info(f"✅ API Key loaded (length: {len(self.api_key)})")

    def test_gpt5_service_import(self):
        """Test GPT-5 service import and initialization"""
        logger.info("🔧 Testing GPT-5 service import...")

        try:
            from gpt5_service_new import GPT5Service
            service = GPT5Service()
            logger.info("✅ GPT-5 service imported and initialized successfully")
            return service
        except Exception as e:
            logger.error(f"❌ GPT-5 service import failed: {e}")
            raise

    async def test_all_models(self, service):
        """Test all GPT-5 models with various parameters"""
        logger.info("🧪 Testing all GPT-5 models...")

        models_to_test = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat"]
        presets_to_test = ["deterministic", "creative", "fast", "detailed"]
        verbosity_levels = ["low", "medium", "high"]
        reasoning_efforts = ["minimal", "low", "medium", "high"]

        test_results = []

        # Basic test prompt
        test_prompt = "Analyze the current state of artificial intelligence in 2025. Provide insights on key technological developments and market trends."

        for model in models_to_test:
            logger.info(f"\n🤖 Testing model: {model}")

            for preset in presets_to_test:
                logger.info(f"📋 Testing preset: {preset}")

                try:
                    start_time = datetime.now()

                    # Test basic functionality
                    response = service.send(
                        message=test_prompt,
                        model_id=model,
                        preset=preset
                    )

                    end_time = datetime.now()
                    response_time = (end_time - start_time).total_seconds()

                    test_result = {
                        'model': model,
                        'preset': preset,
                        'success': True,
                        'response_time': response_time,
                        'response_length': len(response) if response else 0,
                        'response_preview': response[:200] + "..." if response and len(response) > 200 else response
                    }

                    logger.info(f"✅ {model} with {preset}: {len(response)} chars in {response_time:.2f}s")

                    # Save full response
                    filename = f"gpt5_test_{model}_{preset}.txt"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(f"Model: {model}\n")
                        f.write(f"Preset: {preset}\n")
                        f.write(f"Response time: {response_time:.2f}s\n")
                        f.write(f"Response length: {len(response)}\n")
                        f.write("=" * 50 + "\n")
                        f.write(response)

                    test_results.append(test_result)

                except Exception as e:
                    logger.error(f"❌ {model} with {preset} failed: {e}")
                    test_results.append({
                        'model': model,
                        'preset': preset,
                        'success': False,
                        'error': str(e)
                    })

        return test_results

    async def test_verbosity_control(self, service):
        """Test verbosity parameter functionality"""
        logger.info("\n🔊 Testing verbosity control...")

        test_prompt = "Explain quantum computing."
        verbosity_results = []

        for verbosity in ["low", "medium", "high"]:
            logger.info(f"📢 Testing verbosity: {verbosity}")

            try:
                start_time = datetime.now()

                response = service.send(
                    message=test_prompt,
                    model_id="gpt-5-mini",
                    preset="deterministic",
                    verbosity=verbosity
                )

                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds()

                result = {
                    'verbosity': verbosity,
                    'success': True,
                    'response_time': response_time,
                    'response_length': len(response),
                    'words_count': len(response.split()),
                    'response_preview': response[:150] + "..."
                }

                logger.info(f"✅ Verbosity {verbosity}: {len(response)} chars, {len(response.split())} words")

                # Save response
                with open(f"gpt5_verbosity_{verbosity}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"Verbosity: {verbosity}\n")
                    f.write(f"Response time: {response_time:.2f}s\n")
                    f.write(f"Response length: {len(response)}\n")
                    f.write(f"Words count: {len(response.split())}\n")
                    f.write("=" * 50 + "\n")
                    f.write(response)

                verbosity_results.append(result)

            except Exception as e:
                logger.error(f"❌ Verbosity {verbosity} failed: {e}")
                verbosity_results.append({
                    'verbosity': verbosity,
                    'success': False,
                    'error': str(e)
                })

        return verbosity_results

    async def test_reasoning_effort(self, service):
        """Test reasoning effort parameter"""
        logger.info("\n🧠 Testing reasoning effort...")

        test_prompt = "Solve this problem step by step: If a company's revenue grows by 15% each year and they started with $1M revenue, what will be their revenue after 5 years?"
        reasoning_results = []

        for effort in ["minimal", "low", "medium", "high"]:
            logger.info(f"🤔 Testing reasoning effort: {effort}")

            try:
                start_time = datetime.now()

                response = service.send(
                    message=test_prompt,
                    model_id="gpt-5",
                    preset="deterministic",
                    reasoning_effort=effort
                )

                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds()

                result = {
                    'reasoning_effort': effort,
                    'success': True,
                    'response_time': response_time,
                    'response_length': len(response),
                    'contains_calculation': any(word in response.lower() for word in ['calculation', 'step', 'formula', 'math'])
                }

                logger.info(f"✅ Reasoning {effort}: {len(response)} chars in {response_time:.2f}s")

                # Save response
                with open(f"gpt5_reasoning_{effort}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"Reasoning effort: {effort}\n")
                    f.write(f"Response time: {response_time:.2f}s\n")
                    f.write(f"Response length: {len(response)}\n")
                    f.write("=" * 50 + "\n")
                    f.write(response)

                reasoning_results.append(result)

            except Exception as e:
                logger.error(f"❌ Reasoning effort {effort} failed: {e}")
                reasoning_results.append({
                    'reasoning_effort': effort,
                    'success': False,
                    'error': str(e)
                })

        return reasoning_results

    async def test_routing_functionality(self, service):
        """Test routing to different models based on task"""
        logger.info("\n🚦 Testing routing functionality...")

        routing_tests = [
            ('qa', "What is the capital of France?"),
            ('code', "Write a Python function to calculate fibonacci numbers"),
            ('chat', "Hello, how are you today?"),
            ('bulk', "Summarize this: AI is transforming industries."),
            ('analysis', "Analyze the implications of AI in healthcare"),
            ('sentiment', "The stock market is performing well today"),
            ('insights', "Provide insights on cryptocurrency trends")
        ]

        routing_results = []

        for task_type, prompt in routing_tests:
            logger.info(f"🎯 Testing routing for task: {task_type}")

            try:
                # Get the model that should be used for this task
                expected_model = service.choose_model(task_type)
                logger.info(f"   Expected model: {expected_model}")

                start_time = datetime.now()

                # Use the routing method
                if task_type == 'qa':
                    response = service.send_qa(prompt)
                elif task_type == 'code':
                    response = service.send_code(prompt)
                elif task_type == 'chat':
                    response = service.send_chat(prompt)
                elif task_type == 'bulk':
                    response = service.send_bulk(prompt)
                else:
                    # For analysis, sentiment, insights - use send with explicit model
                    response = service.send(prompt, model_id=expected_model)

                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds()

                result = {
                    'task_type': task_type,
                    'expected_model': expected_model,
                    'success': True,
                    'response_time': response_time,
                    'response_length': len(response)
                }

                logger.info(f"✅ Task {task_type}: {len(response)} chars in {response_time:.2f}s")

                # Save response
                with open(f"gpt5_routing_{task_type}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"Task type: {task_type}\n")
                    f.write(f"Expected model: {expected_model}\n")
                    f.write(f"Prompt: {prompt}\n")
                    f.write(f"Response time: {response_time:.2f}s\n")
                    f.write("=" * 50 + "\n")
                    f.write(response)

                routing_results.append(result)

            except Exception as e:
                logger.error(f"❌ Routing test {task_type} failed: {e}")
                routing_results.append({
                    'task_type': task_type,
                    'success': False,
                    'error': str(e)
                })

        return routing_results

    async def check_no_gpt4o_references(self, service):
        """Ensure no GPT-4o references in configuration or service"""
        logger.info("\n🚫 Checking for GPT-4o references...")

        issues_found = []

        # Check configuration
        try:
            config = service.config
            config_str = json.dumps(config).lower()

            if 'gpt-4o' in config_str:
                issues_found.append("GPT-4o found in configuration")

            if 'gpt-4' in config_str:
                # Check if it's actually GPT-4o or legitimate GPT-4 reference
                if 'gpt-4o' in config_str:
                    issues_found.append("GPT-4o references found in config")

            # Check models list
            for model in config.get('models', []):
                if 'gpt-4' in model.get('id', '').lower():
                    issues_found.append(f"GPT-4 model found: {model['id']}")

            # Check routing
            routing = config.get('routing', {})
            for task, model in routing.items():
                if 'gpt-4' in model.lower():
                    issues_found.append(f"GPT-4 model in routing: {task} -> {model}")

        except Exception as e:
            logger.error(f"❌ Error checking configuration: {e}")

        if issues_found:
            logger.warning(f"⚠️ Found {len(issues_found)} GPT-4o references:")
            for issue in issues_found:
                logger.warning(f"   - {issue}")
        else:
            logger.info("✅ No GPT-4o references found - configuration is clean")

        return issues_found

    async def run_comprehensive_test(self):
        """Run all comprehensive tests"""
        logger.info("🚀 Starting GPT-5 Comprehensive Testing Suite")
        logger.info("=" * 80)
        logger.info(f"⏰ Started at: {datetime.now()}")

        try:
            # Initialize service
            service = self.test_gpt5_service_import()

            # Run all tests
            logger.info(f"\n📊 Running comprehensive GPT-5 testing...")

            # Test 1: All models and presets
            model_results = await self.test_all_models(service)

            # Test 2: Verbosity control
            verbosity_results = await self.test_verbosity_control(service)

            # Test 3: Reasoning effort
            reasoning_results = await self.test_reasoning_effort(service)

            # Test 4: Routing functionality
            routing_results = await self.test_routing_functionality(service)

            # Test 5: Check for GPT-4o references
            gpt4o_issues = await self.check_no_gpt4o_references(service)

            # Generate summary report
            self.generate_summary_report(
                model_results, verbosity_results, reasoning_results,
                routing_results, gpt4o_issues
            )

            logger.info(f"\n✅ Comprehensive testing completed at: {datetime.now()}")

        except Exception as e:
            logger.error(f"❌ Comprehensive testing failed: {e}")
            raise

    def generate_summary_report(self, model_results, verbosity_results, reasoning_results, routing_results, gpt4o_issues):
        """Generate comprehensive summary report"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 COMPREHENSIVE GPT-5 TEST SUMMARY REPORT")
        logger.info("=" * 80)

        # Model tests summary
        successful_models = sum(1 for r in model_results if r.get('success', False))
        logger.info(f"\n🤖 Model Tests:")
        logger.info(f"   ✅ Successful: {successful_models}/{len(model_results)}")

        if successful_models > 0:
            avg_response_time = sum(r['response_time'] for r in model_results if r.get('success', False)) / successful_models
            avg_response_length = sum(r['response_length'] for r in model_results if r.get('success', False)) / successful_models
            logger.info(f"   ⏱️ Average response time: {avg_response_time:.2f}s")
            logger.info(f"   📏 Average response length: {avg_response_length:.0f} characters")

        # Verbosity tests summary
        successful_verbosity = sum(1 for r in verbosity_results if r.get('success', False))
        logger.info(f"\n🔊 Verbosity Control Tests:")
        logger.info(f"   ✅ Successful: {successful_verbosity}/{len(verbosity_results)}")

        if successful_verbosity > 0:
            for result in verbosity_results:
                if result.get('success', False):
                    logger.info(f"   📢 {result['verbosity']}: {result['words_count']} words, {result['response_time']:.2f}s")

        # Reasoning tests summary
        successful_reasoning = sum(1 for r in reasoning_results if r.get('success', False))
        logger.info(f"\n🧠 Reasoning Effort Tests:")
        logger.info(f"   ✅ Successful: {successful_reasoning}/{len(reasoning_results)}")

        # Routing tests summary
        successful_routing = sum(1 for r in routing_results if r.get('success', False))
        logger.info(f"\n🚦 Routing Tests:")
        logger.info(f"   ✅ Successful: {successful_routing}/{len(routing_results)}")

        # GPT-4o check summary
        logger.info(f"\n🚫 GPT-4o References Check:")
        if gpt4o_issues:
            logger.warning(f"   ⚠️ Issues found: {len(gpt4o_issues)}")
            for issue in gpt4o_issues:
                logger.warning(f"   - {issue}")
        else:
            logger.info(f"   ✅ Clean - no GPT-4o references found")

        # Overall assessment
        total_tests = len(model_results) + len(verbosity_results) + len(reasoning_results) + len(routing_results)
        total_successful = successful_models + successful_verbosity + successful_reasoning + successful_routing
        success_rate = (total_successful / total_tests) * 100 if total_tests > 0 else 0

        logger.info(f"\n🎯 OVERALL ASSESSMENT:")
        logger.info(f"   📊 Total tests: {total_tests}")
        logger.info(f"   ✅ Successful tests: {total_successful}")
        logger.info(f"   📈 Success rate: {success_rate:.1f}%")

        if success_rate >= 90:
            logger.info(f"   🏆 EXCELLENT - GPT-5 integration is fully functional!")
        elif success_rate >= 75:
            logger.info(f"   👍 GOOD - GPT-5 integration is mostly working")
        elif success_rate >= 50:
            logger.info(f"   ⚠️ FAIR - GPT-5 integration has some issues")
        else:
            logger.info(f"   ❌ POOR - GPT-5 integration needs significant fixes")

        logger.info(f"\n📁 Generated files:")
        logger.info("   - gpt5_comprehensive_test.log (detailed test log)")
        logger.info("   - gpt5_test_*.txt (individual test responses)")
        logger.info("   - gpt5_verbosity_*.txt (verbosity test responses)")
        logger.info("   - gpt5_reasoning_*.txt (reasoning test responses)")
        logger.info("   - gpt5_routing_*.txt (routing test responses)")

async def main():
    """Main execution function"""

    print("🚀 GPT-5 Comprehensive Testing Suite (2025)")
    print("=" * 60)

    try:
        tester = GPT5ComprehensiveTester()
        await tester.run_comprehensive_test()

    except Exception as e:
        print(f"❌ Testing suite failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))