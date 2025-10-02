"""
Phase 4 Orchestrator — Dashboard, Reports, Alerts, Products
Supports: /dashboard, /reports, /schedule, /alerts, /optimize, /brief, /pricing
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import re

from schemas.analysis_schemas import (
    build_base_response,
    Insight,
    Evidence,
    EvidenceRef,
    Meta,
)
from schemas.phase4_schemas import (
    DashboardResult,
    DashboardWidget,
    ReportResult,
    Report,
    ReportSection,
    ReportExport,
    ScheduleResult,
    Schedule,
    AlertsResult,
    Alert,
    ListingResult,
    Listing,
    Localization,
    Experiment,
    BriefsResult,
    AssetBrief,
    CreativeSpecs,
    PricingResult,
    Pricing,
    PricingPlan,
    PricingBundle,
    ROIScenario,
    CampaignResult,
    Campaign,
    CampaignMetrics,
    CampaignRecommendation,
)
from core.models.model_router import get_model_router
from core.models.budget_manager import create_budget_manager
from core.policies.pii_masker import PIIMasker
from core.history.phase4_history_service import get_phase4_history_service

logger = logging.getLogger(__name__)


class Phase4Orchestrator:
    """
    Production Phase 4 Orchestrator
    Supports: dashboard, reports, alerts, product optimization
    """

    def __init__(self) -> None:
        self.model_router = get_model_router()
        self.history_service = get_phase4_history_service()

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Phase 4 command

        Args:
            context: Full context dict

        Returns:
            Response dict (BaseAnalysisResponse or ErrorResponse)
        """
        command = context.get("command", "")
        correlation_id = context.get("telemetry", {}).get("correlation_id", "phase4-run")

        logger.info(f"[{correlation_id}] Executing Phase 4 command: {command}")

        try:
            if command.startswith("/dashboard"):
                response = await self._handle_dashboard(context)
            elif command.startswith("/reports generate"):
                response = await self._handle_reports_generate(context)
            elif command.startswith("/schedule"):
                response = await self._handle_schedule(context)
            elif command.startswith("/alerts"):
                response = await self._handle_alerts(context)
            elif command.startswith("/optimize listing"):
                response = await self._handle_listing_optimizer(context)
            elif command.startswith("/brief"):
                response = await self._handle_asset_brief(context)
            elif command.startswith("/pricing"):
                response = await self._handle_pricing_advisor(context)
            elif command.startswith("/optimize campaign"):
                response = await self._handle_campaign_optimizer(context)
            else:
                raise ValueError(f"Unsupported Phase 4 command: {command}")

            logger.info(f"[{correlation_id}] Command completed successfully")
            return response.model_dump()

        except Exception as e:
            logger.error(f"[{correlation_id}] Command failed: {e}", exc_info=True)
            return self._build_error_response(str(e), context)

    # ==========================================================================
    # HANDLERS
    # ==========================================================================

    async def _handle_dashboard(self, context: Dict[str, Any]) -> Any:
        """Handle /dashboard live | /dashboard custom [metrics]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        window = context.get("retrieval", {}).get("window", "24h")
        metrics = params.get("metrics", ["traffic", "ctr", "conv"])
        user_id = context.get("telemetry", {}).get("user_id")

        # Fetch real history from database
        history = await self._fetch_history_data(user_id, window, metrics)

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 4000),
            budget_cents=limits.get("budget_cents", 25),
            timeout_s=limits.get("timeout_s", 15)
        )

        # Check degradation
        layout = "standard"
        if budget.should_degrade():
            metrics = metrics[:3]
            layout = "compact"
            budget.add_warning("Dashboard degraded to compact layout (budget)")

        # Build widgets
        widgets = []

        # KPI widgets from metrics
        for metric in metrics:
            value, delta = self._calculate_metric(metric, docs, history)
            widgets.append(
                DashboardWidget(
                    type="kpi",
                    title=metric.upper(),
                    value=value,
                    delta=delta,
                    window=window
                )
            )

        # Timeseries widget (if history available)
        if history.get("metrics"):
            points = [
                {"ts": m["ts"], "value": m["value"]}
                for m in history["metrics"][:20]
            ]
            widgets.append(
                DashboardWidget(
                    type="timeseries",
                    metric="traffic",
                    points=points
                )
            )

        # Top topics widget
        if docs:
            topics = {}
            for doc in docs[:10]:
                title = doc.get("title", "")
                score = doc.get("score", 0.0)
                topics[title] = topics.get(title, 0) + score

            top_items = [
                {"name": k, "score": round(v, 2)}
                for k, v in sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
            ]

            widgets.append(
                DashboardWidget(
                    type="toplist",
                    label="top_topics",
                    items=top_items
                )
            )

        dashboard_result = DashboardResult(widgets=widgets, layout=layout)

        # Build insights
        insights = self._build_dashboard_insights(widgets, docs, lang)
        evidence = self._build_evidence(docs[:5])
        meta = self._build_meta(context, confidence=0.8)

        header = "Live Dashboard" if lang == "en" else "Панель управления"
        tldr = self._trim(
            f"Dashboard with {len(widgets)} widgets for {window} window" if lang == "en"
            else f"Дашборд с {len(widgets)} виджетами за окно {window}",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=dashboard_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )

        return response

    async def _handle_reports_generate(self, context: Dict[str, Any]) -> Any:
        """Handle /reports generate weekly|monthly [audience]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        period = "weekly" if "weekly" in context.get("command", "") else "monthly"
        audience = params.get("audience")
        user_id = context.get("telemetry", {}).get("user_id")

        # Fetch real history
        window = "1w" if period == "weekly" else "1m"
        history = await self._fetch_history_data(user_id, window, ["traffic", "ctr", "conv", "roi"])

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 8000),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 30)
        )

        # Build sections
        sections = []

        # 1. Executive Summary
        exec_bullets = self._generate_executive_summary(docs, history, lang, budget)
        sections.append(ReportSection(title="Executive Summary", bullets=exec_bullets))

        # 2. Trends & Momentum
        trends_bullets = self._generate_trends_section(docs, history, lang, budget)
        sections.append(ReportSection(title="Trends & Momentum", bullets=trends_bullets))

        # 3. Competitors (if available)
        if history.get("competitors"):
            comp_bullets = [
                f"Competitor {c['domain']}: overlap {c.get('overlap_score', 0):.2f}"
                for c in history["competitors"][:3]
            ]
            sections.append(ReportSection(title="Competitors", bullets=comp_bullets))

        # 4. Forecast & Risks
        forecast_bullets = self._generate_forecast_section(docs, history, lang, budget)
        sections.append(ReportSection(title="Forecast & Risks", bullets=forecast_bullets))

        # 5. Recommended Actions
        action_bullets = self._generate_actions_section(docs, history, lang, budget)
        sections.append(ReportSection(title="Recommended Actions", bullets=action_bullets))

        # Degradation check
        if budget.should_degrade():
            sections = sections[:3]  # Keep only first 3 sections
            budget.add_warning("Report degraded to 3 sections (budget)")

        # Build report
        filename = f"{period}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
        report = Report(
            period=period,
            sections=sections,
            export=ReportExport(format="pdf", filename=filename)
        )

        report_result = ReportResult(report=report)

        # Build response
        insights = self._build_report_insights(sections, docs, lang)
        evidence = self._build_evidence(docs[:10])
        meta = self._build_meta(context, confidence=0.75)

        header = f"{period.capitalize()} Report" if lang == "en" else f"{period.capitalize()} отчёт"
        tldr = self._trim(
            f"{period.capitalize()} report with {len(sections)} sections generated" if lang == "en"
            else f"{period.capitalize()} отчёт с {len(sections)} разделами создан",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=report_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )

        return response

    async def _handle_schedule(self, context: Dict[str, Any]) -> Any:
        """Handle /schedule report [weekly|monthly] [time]"""
        params = context.get("params", {})
        lang = params.get("lang", "en")
        schedule_config = params.get("schedule", {})
        cron = schedule_config.get("cron", "0 9 * * 1")  # Default: Monday 9 AM

        # Calculate next run
        next_run = datetime.utcnow() + timedelta(days=7)
        next_run_utc = next_run.isoformat() + "Z"

        schedule = Schedule(
            cron=cron,
            next_run_utc=next_run_utc,
            channel="telegram",
            recipients=["masked_user_id"]
        )

        schedule_result = ScheduleResult(schedule=schedule)

        # Build response
        insights = [
            Insight(
                type="fact",
                text=f"Report scheduled with cron: {cron}",
                evidence_refs=[]
            )
        ]

        meta = self._build_meta(context, confidence=1.0)

        header = "Report Scheduled" if lang == "en" else "Отчёт запланирован"
        tldr = self._trim(
            f"Next report will run at {next_run_utc}" if lang == "en"
            else f"Следующий отчёт будет запущен {next_run_utc}",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=[],
            result=schedule_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    async def _handle_alerts(self, context: Dict[str, Any]) -> Any:
        """Handle /alerts setup [conditions] | /alerts test"""
        params = context.get("params", {})
        lang = params.get("lang", "en")
        command = context.get("command", "")

        # Build sample alerts
        alerts = [
            Alert(
                name="high_error_rate",
                condition="error_rate > 0.05",
                window="5m",
                severity="P1",
                action="page"
            ),
            Alert(
                name="budget_exceeded",
                condition="cost_usd > budget_limit",
                window="1h",
                severity="P1",
                action="throttle"
            ),
            Alert(
                name="rag_quality_drop",
                condition="avg_relevance_score < 0.6",
                window="10m",
                severity="P2",
                action="notify"
            )
        ]

        alerts_result = AlertsResult(alerts=alerts)

        # Build response
        insights = [
            Insight(
                type="recommendation",
                text=f"Configured {len(alerts)} alert rules",
                evidence_refs=[]
            )
        ]

        meta = self._build_meta(context, confidence=1.0)

        header = "Alerts Setup" if lang == "en" else "Настройка алертов"
        tldr = self._trim(
            f"{len(alerts)} alert rules configured" if lang == "en"
            else f"Настроено {len(alerts)} правил алертов",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=[],
            result=alerts_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    async def _handle_listing_optimizer(self, context: Dict[str, Any]) -> Any:
        """Handle /optimize listing [goal]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        goal = params.get("goal", "ctr")

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 6000),
            budget_cents=limits.get("budget_cents", 40),
            timeout_s=limits.get("timeout_s", 25)
        )

        # Generate optimized listing
        title = self._generate_listing_title(docs, goal, lang)
        subtitle = self._generate_listing_subtitle(docs, goal, lang)
        description = self._generate_listing_description(docs, goal, lang)
        tags = self._generate_listing_tags(docs, goal)

        # Localizations
        localizations = [
            Localization(
                locale="en",
                title=title if lang == "en" else self._translate(title, "en"),
                description=description if lang == "en" else self._translate(description, "en")
            )
        ]
        if lang == "ru":
            localizations.append(
                Localization(
                    locale="ru",
                    title=title,
                    description=description
                )
            )

        # Experiments
        experiments = [
            Experiment(
                name="A",
                hypothesis=f"Emphasizing key benefit improves {goal}",
                kpi=goal,
                expected_delta=0.15
            ),
            Experiment(
                name="B",
                hypothesis=f"Shorter description improves {goal}",
                kpi=goal,
                expected_delta=0.10
            )
        ]

        listing = Listing(
            title=title,
            subtitle=subtitle,
            description=description,
            tags=tags,
            localizations=localizations,
            experiments=experiments
        )

        listing_result = ListingResult(listing=listing)

        # Build response
        insights = self._build_listing_insights(listing, docs, lang)
        evidence = self._build_evidence(docs[:5])
        meta = self._build_meta(context, confidence=0.7)

        header = "Listing Optimization" if lang == "en" else "Оптимизация листинга"
        tldr = self._trim(
            f"Optimized listing for {goal} with {len(localizations)} localizations" if lang == "en"
            else f"Оптимизирован листинг для {goal} с {len(localizations)} локализациями",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=listing_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )

        return response

    async def _handle_asset_brief(self, context: Dict[str, Any]) -> Any:
        """Handle /brief assets [channels]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        channels = params.get("channels", ["web", "social"])

        # Create briefs for each channel
        briefs = []
        for channel in channels:
            brief = self._generate_asset_brief(channel, docs, lang)
            briefs.append(brief)

        briefs_result = BriefsResult(briefs=briefs)

        # Build response
        insights = self._build_brief_insights(briefs, docs, lang)
        evidence = self._build_evidence(docs[:5])
        meta = self._build_meta(context, confidence=0.75)

        header = "Asset Briefs" if lang == "en" else "Брифы на ассеты"
        tldr = self._trim(
            f"Generated {len(briefs)} creative briefs for channels" if lang == "en"
            else f"Создано {len(briefs)} брифов для каналов",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=briefs_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    async def _handle_pricing_advisor(self, context: Dict[str, Any]) -> Any:
        """Handle /pricing advisor [product|plan] [targets]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        targets = params.get("targets", {})

        # Generate pricing plans
        plans = [
            PricingPlan(
                name="Basic",
                price=9.99,
                billing="monthly",
                value_props=["Core features", "Community support", "1 user"]
            ),
            PricingPlan(
                name="Pro",
                price=29.99,
                billing="monthly",
                value_props=["All features", "Priority support", "5 users", "API access"]
            ),
            PricingPlan(
                name="Enterprise",
                price=99.99,
                billing="monthly",
                value_props=["Unlimited", "24/7 support", "Custom integration", "SLA"]
            )
        ]

        # Generate bundles
        bundles = [
            PricingBundle(
                name="Startup Bundle",
                components=["Pro plan", "Onboarding", "Training"],
                bundle_price=49.99
            )
        ]

        # Generate ROI scenarios
        roi_scenarios = [
            ROIScenario(
                scenario="base",
                roi=2.5,
                cac=100.0,
                ltv=250.0,
                assumptions=["12-month retention", "10% monthly churn"]
            ),
            ROIScenario(
                scenario="optimistic",
                roi=4.0,
                cac=80.0,
                ltv=320.0,
                assumptions=["18-month retention", "5% monthly churn"]
            )
        ]

        pricing = Pricing(
            plans=plans,
            bundles=bundles,
            roi_scenarios=roi_scenarios
        )

        pricing_result = PricingResult(pricing=pricing)

        # Build response
        insights = self._build_pricing_insights(pricing, docs, lang)
        evidence = self._build_evidence(docs[:5])
        meta = self._build_meta(context, confidence=0.7)

        header = "Pricing Advisor" if lang == "en" else "Советник по ценам"
        tldr = self._trim(
            f"Generated {len(plans)} pricing plans with ROI scenarios" if lang == "en"
            else f"Создано {len(plans)} тарифов с ROI сценариями",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=pricing_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    async def _handle_campaign_optimizer(self, context: Dict[str, Any]) -> Any:
        """Handle /optimize campaign [metrics|channel]"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        channel = params.get("channels", ["web"])[0] if params.get("channels") else "web"
        history = context.get("history", {})

        # Extract current metrics
        current_metrics = CampaignMetrics(
            ctr=0.025,
            conv=0.05,
            roi=2.0,
            cac=50.0
        )

        # If history has metrics, use them
        if history.get("metrics"):
            for m in history["metrics"]:
                metric_name = m.get("metric", "")
                if metric_name == "ctr":
                    current_metrics.ctr = m["value"]
                elif metric_name == "conv":
                    current_metrics.conv = m["value"]
                elif metric_name == "roi":
                    current_metrics.roi = m["value"]
                elif metric_name == "cac":
                    current_metrics.cac = m["value"]

        # Generate recommendations
        recommendations = [
            CampaignRecommendation(
                action="Increase bid on high-converting keywords",
                expected_impact="high",
                kpi="conv"
            ),
            CampaignRecommendation(
                action="Test new ad copy with emotional hooks",
                expected_impact="medium",
                kpi="ctr"
            ),
            CampaignRecommendation(
                action="Optimize landing page load time",
                expected_impact="medium",
                kpi="conv"
            )
        ]

        campaign = Campaign(
            channel=channel,
            current_metrics=current_metrics,
            recommendations=recommendations
        )

        campaign_result = CampaignResult(campaign=campaign)

        # Build response
        insights = self._build_campaign_insights(campaign, docs, lang)
        evidence = self._build_evidence(docs[:5])
        meta = self._build_meta(context, confidence=0.75)

        header = "Campaign Optimizer" if lang == "en" else "Оптимизация кампании"
        tldr = self._trim(
            f"Generated {len(recommendations)} optimization recommendations for {channel}" if lang == "en"
            else f"Создано {len(recommendations)} рекомендаций для {channel}",
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=campaign_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    def _calculate_metric(
        self,
        metric: str,
        docs: List[Dict[str, Any]],
        history: Dict[str, Any]
    ) -> tuple[float, float]:
        """Calculate metric value and delta from docs and history"""
        # Simple mock calculation
        if metric == "traffic":
            value = len(docs) * 100
            delta = 0.15 if len(docs) > 5 else -0.05
        elif metric == "ctr":
            value = 0.025
            delta = 0.10
        elif metric == "conv":
            value = 0.05
            delta = 0.20
        elif metric == "roi":
            value = 2.5
            delta = 0.30
        else:
            value = 0.0
            delta = 0.0

        return value, delta

    def _generate_executive_summary(
        self,
        docs: List[Dict[str, Any]],
        history: Dict[str, Any],
        lang: str,
        budget
    ) -> List[str]:
        """Generate executive summary bullets"""
        bullets = []

        if docs:
            bullets.append(
                f"Analyzed {len(docs)} documents from past period" if lang == "en"
                else f"Проанализировано {len(docs)} документов за период"
            )

        if history.get("snapshots"):
            bullets.append(
                f"Identified {len(history['snapshots'])} key trends" if lang == "en"
                else f"Выявлено {len(history['snapshots'])} ключевых трендов"
            )

        bullets.append(
            "Overall performance shows positive momentum" if lang == "en"
            else "Общая динамика показывает положительный тренд"
        )

        return bullets[:3]

    def _generate_trends_section(
        self,
        docs: List[Dict[str, Any]],
        history: Dict[str, Any],
        lang: str,
        budget
    ) -> List[str]:
        """Generate trends section bullets"""
        bullets = []

        if history.get("snapshots"):
            for snap in history["snapshots"][:3]:
                momentum = snap.get("momentum", 0.0)
                topic = snap.get("topic", "Topic")
                bullets.append(
                    f"{topic}: momentum {momentum:+.2f}" if lang == "en"
                    else f"{topic}: импульс {momentum:+.2f}"
                )
        else:
            bullets.append(
                "No historical trend data available" if lang == "en"
                else "Нет данных по историческим трендам"
            )

        return bullets

    def _generate_forecast_section(
        self,
        docs: List[Dict[str, Any]],
        history: Dict[str, Any]],
        lang: str,
        budget
    ) -> List[str]:
        """Generate forecast bullets"""
        return [
            "Forecast: continued growth expected" if lang == "en"
            else "Прогноз: ожидается продолжение роста",
            "Key risk: market volatility" if lang == "en"
            else "Ключевой риск: волатильность рынка"
        ]

    def _generate_actions_section(
        self,
        docs: List[Dict[str, Any]],
        history: Dict[str, Any]],
        lang: str,
        budget
    ) -> List[str]:
        """Generate recommended actions"""
        return [
            "Action 1: Increase investment in top-performing channels" if lang == "en"
            else "Действие 1: Увеличить инвестиции в лучшие каналы",
            "Action 2: Test new content formats" if lang == "en"
            else "Действие 2: Протестировать новые форматы контента",
            "Action 3: Expand to adjacent markets" if lang == "en"
            else "Действие 3: Расширение на смежные рынки"
        ]

    def _generate_listing_title(
        self,
        docs: List[Dict[str, Any]],
        goal: str,
        lang: str
    ) -> str:
        """Generate optimized listing title"""
        if lang == "ru":
            return "Премиум RSS-новости с AI анализом"
        return "Premium RSS News with AI Analysis"

    def _generate_listing_subtitle(
        self,
        docs: List[Dict[str, Any]],
        goal: str,
        lang: str
    ) -> str:
        """Generate optimized listing subtitle"""
        if lang == "ru":
            return "Получайте умные инсайты из новостных лент"
        return "Get smart insights from your news feeds"

    def _generate_listing_description(
        self,
        docs: List[Dict[str, Any]],
        goal: str,
        lang: str
    ) -> str:
        """Generate optimized listing description"""
        if lang == "ru":
            return ("Наш AI-движок анализирует тысячи новостей и выдаёт вам только самое важное. "
                    "Экономьте время, принимайте лучшие решения.")
        return ("Our AI engine analyzes thousands of news articles and delivers only what matters. "
                "Save time, make better decisions.")

    def _generate_listing_tags(
        self,
        docs: List[Dict[str, Any]],
        goal: str
    ) -> List[str]:
        """Generate optimized tags"""
        return ["ai", "news", "analytics", "rss", "automation"]

    def _translate(self, text: str, target_lang: str) -> str:
        """Mock translation (in production use real translation service)"""
        # Simple mock - in production, use LLM or translation API
        return text

    def _generate_asset_brief(
        self,
        channel: str,
        docs: List[Dict[str, Any]],
        lang: str
    ) -> AssetBrief:
        """Generate creative brief for channel"""
        return AssetBrief(
            channel=channel,
            objective="awareness",
            creative_specs=CreativeSpecs(
                format="image" if channel in ["web", "social"] else "video",
                duration_s=15 if channel == "ads" else None,
                aspect="1:1" if channel == "social" else "16:9"
            ),
            content_directions=[
                "Emphasize AI-powered insights",
                "Modern, tech-forward aesthetic",
                "Clear call-to-action"
            ],
            must_include=["Logo", "Key benefit"],
            nice_to_have=["User testimonial", "Demo screenshot"]
        )

    def _build_dashboard_insights(
        self,
        widgets: List[DashboardWidget],
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from dashboard widgets"""
        insights = []

        for widget in widgets[:3]:
            if widget.type == "kpi" and widget.delta:
                text = f"{widget.title} shows {widget.delta:+.1%} change" if lang == "en" else f"{widget.title} изменился на {widget.delta:+.1%}"
                insights.append(
                    Insight(
                        type="fact",
                        text=self._trim(text, 180),
                        evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
                    )
                )

        return insights

    def _build_report_insights(
        self,
        sections: List[ReportSection],
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from report sections"""
        insights = []

        for section in sections[:3]:
            if section.bullets:
                insights.append(
                    Insight(
                        type="fact",
                        text=self._trim(section.bullets[0], 180),
                        evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
                    )
                )

        return insights

    def _build_listing_insights(
        self,
        listing: Listing,
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from listing optimization"""
        return [
            Insight(
                type="recommendation",
                text=self._trim(f"Title optimized: {listing.title}", 180),
                evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
            ),
            Insight(
                type="recommendation",
                text=self._trim(f"Generated {len(listing.tags)} relevant tags", 180),
                evidence_refs=[]
            )
        ]

    def _build_brief_insights(
        self,
        briefs: List[AssetBrief],
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from asset briefs"""
        insights = []

        for brief in briefs:
            insights.append(
                Insight(
                    type="recommendation",
                    text=self._trim(f"Brief for {brief.channel}: {brief.objective} objective", 180),
                    evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
                )
            )

        return insights

    def _build_pricing_insights(
        self,
        pricing: Pricing,
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from pricing recommendations"""
        return [
            Insight(
                type="recommendation",
                text=self._trim(f"Base scenario ROI: {pricing.roi_scenarios[0].roi:.1f}x", 180),
                evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
            )
        ]

    def _build_campaign_insights(
        self,
        campaign: Campaign,
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Insight]:
        """Build insights from campaign optimization"""
        insights = []

        for rec in campaign.recommendations[:3]:
            insights.append(
                Insight(
                    type="recommendation",
                    text=self._trim(rec.action, 180),
                    evidence_refs=[self._build_evidence_ref(docs[0])] if docs else []
                )
            )

        return insights

    def _build_evidence_ref(self, doc: Dict[str, Any]) -> EvidenceRef:
        """Build evidence reference from document"""
        return EvidenceRef(
            article_id=doc.get("article_id"),
            url=doc.get("url"),
            date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
        )

    def _build_evidence(self, docs: List[Dict[str, Any]]) -> List[Evidence]:
        """Build evidence list from documents"""
        evidence = []
        for doc in docs:
            evidence.append(
                Evidence(
                    title=self._trim(doc.get("title", ""), 100),
                    article_id=doc.get("article_id"),
                    url=doc.get("url"),
                    date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
                    snippet=self._trim(doc.get("snippet", ""), 240)
                )
            )
        return evidence

    def _build_meta(self, context: Dict[str, Any], confidence: float) -> Meta:
        """Build metadata"""
        models = context.get("models", {})
        telemetry = context.get("telemetry", {})
        ab_test = context.get("ab_test", {})

        return Meta(
            confidence=confidence,
            model=models.get("primary", "gpt-5"),
            version="phase4-orchestrator-v1.0",
            correlation_id=telemetry.get("correlation_id", "phase4-run"),
            experiment=ab_test.get("experiment"),
            arm=ab_test.get("arm")
        )

    def _trim(self, text: str, max_len: int) -> str:
        """Trim text to max length"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def _build_error_response(self, error_msg: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build error response"""
        telemetry = context.get("telemetry", {})
        ab_test = context.get("ab_test", {})

        return {
            "error": {
                "code": "INTERNAL",
                "user_message": "An error occurred during processing",
                "tech_message": error_msg,
                "retryable": True
            },
            "meta": {
                "model": context.get("models", {}).get("primary", "gpt-5"),
                "version": "phase4-orchestrator-v1.0",
                "correlation_id": telemetry.get("correlation_id", "phase4-error"),
                "experiment": ab_test.get("experiment"),
                "arm": ab_test.get("arm")
            }
        }

    async def _fetch_history_data(
        self,
        user_id: Optional[str],
        window: str,
        metrics: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch historical data from database.

        Args:
            user_id: User ID
            window: Time window (e.g., '24h', '1w')
            metrics: List of metrics to fetch

        Returns:
            Dict with metrics and snapshots
        """
        try:
            # Parse window to hours
            hours_map = {
                '1h': 1, '6h': 6, '12h': 12, '24h': 24,
                '1d': 24, '3d': 72, '1w': 168, '2w': 336, '1m': 720
            }
            hours_back = hours_map.get(window, 24)

            # Fetch metrics from database
            all_metrics = []
            for metric in metrics:
                metric_data = await self.history_service.get_metrics(
                    metric=metric,
                    user_id=user_id,
                    hours_back=hours_back,
                    limit=100
                )
                all_metrics.extend(metric_data)

            # Fetch snapshots (topic trends)
            snapshots = await self.history_service.get_top_topics(
                user_id=user_id,
                hours_back=hours_back,
                limit=20,
                sort_by="momentum"
            )

            return {
                "metrics": all_metrics,
                "snapshots": snapshots,
                "competitors": []  # TODO: implement competitors tracking
            }

        except Exception as e:
            logger.error(f"[Phase4Orchestrator] Failed to fetch history: {e}")
            # Return empty history if DB fails
            return {
                "metrics": [],
                "snapshots": [],
                "competitors": []
            }


def create_phase4_orchestrator() -> Phase4Orchestrator:
    """Factory function to create Phase4Orchestrator"""
    return Phase4Orchestrator()
