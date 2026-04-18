#!/usr/bin/env python3
"""Generate all 137 Blufire agent YAML definitions for Ruflo swarm."""

import os
import yaml

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "agents")

# All 137 agents organized by domain
AGENT_DEFINITIONS = {
    "core": [
        {"name": "coordinator", "desc": "Orchestrates agent workflows and task routing", "caps": ["task_routing", "workflow_management", "agent_coordination", "priority_scheduling"]},
        {"name": "coder", "desc": "Writes, refactors, and debugs code across languages", "caps": ["code_generation", "refactoring", "debugging", "multi_language"]},
        {"name": "tester", "desc": "Writes and executes tests using TDD methodology", "caps": ["unit_testing", "integration_testing", "tdd", "test_coverage"]},
        {"name": "reviewer", "desc": "Reviews code quality, style, and best practices", "caps": ["code_review", "style_enforcement", "best_practices", "security_review"]},
        {"name": "architect", "desc": "Designs system architecture and API contracts", "caps": ["system_design", "api_design", "documentation", "technical_specs"]},
        {"name": "researcher", "desc": "Analyzes requirements and researches solutions", "caps": ["requirement_analysis", "solution_research", "competitive_analysis", "feasibility"]},
    ],
    "sales": [
        {"name": "lead-prospector", "desc": "Identifies and qualifies potential leads from multiple sources", "caps": ["apollo_search", "lead_scoring", "prospect_identification", "data_enrichment"]},
        {"name": "lead-scorer", "desc": "AI-powered lead scoring based on fit and intent signals", "caps": ["scoring_models", "intent_detection", "fit_analysis", "predictive_scoring"]},
        {"name": "outbound-caller", "desc": "Manages outbound call sequences and scripts", "caps": ["call_scripting", "sequence_management", "voicemail_drops", "call_logging"]},
        {"name": "email-sequencer", "desc": "Creates and manages multi-step email sequences", "caps": ["sequence_design", "ab_testing", "send_optimization", "reply_detection"]},
        {"name": "deal-creator", "desc": "Creates and configures new deals in CRM pipeline", "caps": ["deal_creation", "pipeline_management", "stage_assignment", "value_estimation"]},
        {"name": "deal-progressor", "desc": "Moves deals through pipeline stages based on signals", "caps": ["stage_progression", "signal_detection", "automation_rules", "milestone_tracking"]},
        {"name": "proposal-writer", "desc": "Generates customized proposals and quotes", "caps": ["proposal_generation", "pricing_calculation", "template_management", "customization"]},
        {"name": "contract-manager", "desc": "Manages contract creation, review, and signing workflows", "caps": ["contract_generation", "review_workflow", "e_signature", "compliance_check"]},
        {"name": "pipeline-analyst", "desc": "Analyzes pipeline health and forecasts revenue", "caps": ["pipeline_analysis", "revenue_forecasting", "bottleneck_detection", "win_rate_analysis"]},
        {"name": "competitor-tracker", "desc": "Monitors competitor activities and market positioning", "caps": ["competitor_monitoring", "market_intelligence", "pricing_comparison", "feature_tracking"]},
        {"name": "crm-syncer", "desc": "Synchronizes data across CRM and external platforms", "caps": ["hubspot_sync", "data_mapping", "conflict_resolution", "bulk_operations"]},
        {"name": "follow-up-agent", "desc": "Manages follow-up cadences and touchpoint scheduling", "caps": ["cadence_management", "touchpoint_scheduling", "reminder_creation", "engagement_tracking"]},
        {"name": "objection-handler", "desc": "Provides real-time objection handling strategies", "caps": ["objection_analysis", "response_generation", "battlecard_lookup", "coaching"]},
        {"name": "territory-manager", "desc": "Manages sales territory assignments and balancing", "caps": ["territory_assignment", "workload_balancing", "geo_mapping", "account_routing"]},
        {"name": "referral-tracker", "desc": "Tracks and manages referral programs and introductions", "caps": ["referral_tracking", "reward_management", "introduction_requests", "network_mapping"]},
    ],
    "marketing": [
        {"name": "campaign-planner", "desc": "Plans and structures marketing campaigns", "caps": ["campaign_design", "audience_targeting", "budget_allocation", "timeline_planning"]},
        {"name": "content-strategist", "desc": "Develops content strategy aligned with marketing goals", "caps": ["content_planning", "topic_research", "editorial_calendar", "content_gaps"]},
        {"name": "seo-optimizer", "desc": "Optimizes content and pages for search engine rankings", "caps": ["keyword_research", "on_page_seo", "technical_seo", "rank_tracking"]},
        {"name": "social-media-agent", "desc": "Manages social media posting and engagement", "caps": ["post_scheduling", "engagement_monitoring", "hashtag_strategy", "platform_optimization"]},
        {"name": "email-marketer", "desc": "Designs and executes email marketing campaigns", "caps": ["newsletter_design", "segmentation", "automation_workflows", "deliverability"]},
        {"name": "ad-manager", "desc": "Manages paid advertising across platforms", "caps": ["ad_creation", "bid_management", "audience_targeting", "budget_optimization"]},
        {"name": "landing-page-builder", "desc": "Creates and optimizes landing pages for conversions", "caps": ["page_design", "ab_testing", "conversion_optimization", "form_builder"]},
        {"name": "brand-monitor", "desc": "Monitors brand mentions and sentiment across channels", "caps": ["mention_tracking", "sentiment_analysis", "alert_management", "reputation_scoring"]},
        {"name": "event-coordinator", "desc": "Plans and coordinates marketing events and webinars", "caps": ["event_planning", "registration_management", "promotion", "follow_up"]},
        {"name": "influencer-scout", "desc": "Identifies and manages influencer partnerships", "caps": ["influencer_discovery", "outreach", "relationship_management", "roi_tracking"]},
        {"name": "analytics-reporter", "desc": "Generates marketing analytics reports and insights", "caps": ["data_collection", "report_generation", "trend_analysis", "roi_calculation"]},
        {"name": "audience-segmenter", "desc": "Segments audiences for targeted marketing", "caps": ["behavioral_segmentation", "demographic_analysis", "lookalike_modeling", "segment_optimization"]},
    ],
    "support": [
        {"name": "ticket-router", "desc": "Routes support tickets to appropriate agents or teams", "caps": ["ticket_classification", "priority_assignment", "skill_based_routing", "escalation"]},
        {"name": "chat-responder", "desc": "Handles real-time chat support inquiries", "caps": ["live_chat", "response_generation", "context_awareness", "handoff_management"]},
        {"name": "knowledge-base-agent", "desc": "Maintains and searches knowledge base for answers", "caps": ["article_search", "content_creation", "gap_identification", "version_management"]},
        {"name": "escalation-manager", "desc": "Manages escalation paths and SLA compliance", "caps": ["escalation_routing", "sla_monitoring", "priority_override", "notification_management"]},
        {"name": "feedback-collector", "desc": "Collects and processes customer feedback", "caps": ["survey_management", "nps_tracking", "feedback_analysis", "trend_reporting"]},
        {"name": "onboarding-guide", "desc": "Guides new customers through onboarding process", "caps": ["onboarding_flows", "milestone_tracking", "resource_delivery", "success_metrics"]},
        {"name": "bug-reporter", "desc": "Collects bug reports and creates structured tickets", "caps": ["bug_collection", "reproduction_steps", "priority_classification", "assignment"]},
        {"name": "satisfaction-tracker", "desc": "Tracks customer satisfaction metrics and trends", "caps": ["csat_measurement", "trend_analysis", "alert_triggers", "improvement_suggestions"]},
        {"name": "faq-updater", "desc": "Automatically updates FAQs based on common inquiries", "caps": ["pattern_detection", "content_generation", "approval_workflow", "publishing"]},
        {"name": "sla-monitor", "desc": "Monitors SLA compliance and alerts on violations", "caps": ["sla_tracking", "violation_alerts", "performance_reporting", "threshold_management"]},
    ],
    "analytics": [
        {"name": "data-collector", "desc": "Collects and aggregates data from multiple sources", "caps": ["api_integration", "data_extraction", "scheduling", "validation"]},
        {"name": "metrics-tracker", "desc": "Tracks KPIs and business metrics in real-time", "caps": ["kpi_monitoring", "threshold_alerts", "trend_detection", "dashboard_updates"]},
        {"name": "report-generator", "desc": "Generates automated reports on schedule", "caps": ["report_templates", "data_visualization", "scheduling", "distribution"]},
        {"name": "trend-analyzer", "desc": "Identifies trends and patterns in business data", "caps": ["time_series_analysis", "pattern_recognition", "anomaly_detection", "forecasting"]},
        {"name": "ab-test-analyzer", "desc": "Analyzes A/B test results with statistical rigor", "caps": ["statistical_testing", "significance_calculation", "sample_size_estimation", "recommendation"]},
        {"name": "cohort-analyzer", "desc": "Performs cohort analysis for retention and behavior", "caps": ["cohort_definition", "retention_analysis", "behavior_tracking", "lifecycle_mapping"]},
        {"name": "funnel-optimizer", "desc": "Analyzes and optimizes conversion funnels", "caps": ["funnel_mapping", "drop_off_analysis", "optimization_suggestions", "impact_estimation"]},
        {"name": "attribution-modeler", "desc": "Builds multi-touch attribution models", "caps": ["touchpoint_tracking", "model_building", "channel_attribution", "roi_calculation"]},
        {"name": "predictive-modeler", "desc": "Builds predictive models for business outcomes", "caps": ["model_training", "feature_engineering", "prediction", "model_monitoring"]},
        {"name": "dashboard-builder", "desc": "Creates and maintains analytics dashboards", "caps": ["widget_design", "data_binding", "layout_management", "refresh_scheduling"]},
    ],
    "engineering": [
        {"name": "frontend-dev", "desc": "Develops frontend interfaces and components", "caps": ["react", "typescript", "css", "responsive_design"]},
        {"name": "backend-dev", "desc": "Develops backend services and APIs", "caps": ["api_development", "database_design", "authentication", "performance"]},
        {"name": "api-designer", "desc": "Designs RESTful and GraphQL API contracts", "caps": ["api_design", "schema_definition", "versioning", "documentation"]},
        {"name": "database-admin", "desc": "Manages database schemas, queries, and optimization", "caps": ["schema_design", "query_optimization", "migration", "backup"]},
        {"name": "migration-agent", "desc": "Handles data and schema migrations safely", "caps": ["schema_migration", "data_migration", "rollback_planning", "validation"]},
        {"name": "performance-optimizer", "desc": "Optimizes application and infrastructure performance", "caps": ["profiling", "bottleneck_detection", "caching", "load_testing"]},
        {"name": "dependency-manager", "desc": "Manages dependencies and updates across projects", "caps": ["version_tracking", "vulnerability_scanning", "update_planning", "compatibility"]},
        {"name": "documentation-writer", "desc": "Writes and maintains technical documentation", "caps": ["api_docs", "guides", "architecture_docs", "changelog"]},
        {"name": "refactoring-agent", "desc": "Identifies and executes code refactoring opportunities", "caps": ["code_analysis", "pattern_detection", "safe_refactoring", "test_preservation"]},
        {"name": "error-handler", "desc": "Implements error handling and recovery patterns", "caps": ["error_classification", "retry_logic", "circuit_breakers", "graceful_degradation"]},
        {"name": "webhook-manager", "desc": "Manages webhook configurations and event processing", "caps": ["webhook_setup", "event_routing", "payload_validation", "retry_management"]},
        {"name": "cache-manager", "desc": "Manages caching strategies and invalidation", "caps": ["cache_strategy", "invalidation_rules", "warm_up", "monitoring"]},
    ],
    "content": [
        {"name": "blog-writer", "desc": "Writes blog posts optimized for SEO and engagement", "caps": ["blog_writing", "seo_optimization", "tone_matching", "cta_integration"]},
        {"name": "copywriter", "desc": "Writes marketing copy for ads, emails, and landing pages", "caps": ["ad_copy", "email_copy", "landing_page_copy", "headline_generation"]},
        {"name": "social-writer", "desc": "Creates social media posts and thread content", "caps": ["platform_optimization", "hashtag_strategy", "visual_suggestions", "engagement_hooks"]},
        {"name": "case-study-writer", "desc": "Creates customer case studies and success stories", "caps": ["interview_synthesis", "narrative_structure", "data_presentation", "approval_workflow"]},
        {"name": "whitepaper-writer", "desc": "Writes in-depth whitepapers and research reports", "caps": ["research_synthesis", "data_analysis", "technical_writing", "citation_management"]},
        {"name": "newsletter-curator", "desc": "Curates and assembles newsletter content", "caps": ["content_curation", "theme_selection", "layout_design", "personalization"]},
        {"name": "video-scripter", "desc": "Writes scripts for video content and presentations", "caps": ["script_writing", "storyboarding", "timing_optimization", "cta_placement"]},
        {"name": "press-release-writer", "desc": "Drafts press releases and media communications", "caps": ["press_writing", "quote_generation", "distribution_prep", "media_list"]},
        {"name": "template-designer", "desc": "Creates reusable content templates", "caps": ["template_creation", "variable_management", "style_consistency", "version_control"]},
        {"name": "editor", "desc": "Reviews and edits content for quality and consistency", "caps": ["grammar_check", "style_enforcement", "fact_checking", "tone_consistency"]},
    ],
    "research": [
        {"name": "market-researcher", "desc": "Conducts market research and competitive analysis", "caps": ["market_sizing", "trend_analysis", "competitor_profiling", "opportunity_mapping"]},
        {"name": "industry-analyst", "desc": "Analyzes industry trends and developments", "caps": ["industry_monitoring", "report_generation", "expert_synthesis", "prediction"]},
        {"name": "customer-researcher", "desc": "Researches customer needs, behaviors, and preferences", "caps": ["persona_development", "journey_mapping", "needs_analysis", "survey_design"]},
        {"name": "technology-scout", "desc": "Scouts emerging technologies and tools", "caps": ["tech_monitoring", "evaluation", "poc_planning", "adoption_recommendation"]},
        {"name": "patent-analyzer", "desc": "Analyzes patent landscapes and IP opportunities", "caps": ["patent_search", "landscape_analysis", "freedom_to_operate", "filing_recommendations"]},
        {"name": "pricing-researcher", "desc": "Researches pricing strategies and market rates", "caps": ["price_benchmarking", "elasticity_analysis", "competitive_pricing", "value_modeling"]},
        {"name": "data-miner", "desc": "Extracts insights from large datasets", "caps": ["data_extraction", "pattern_mining", "correlation_analysis", "insight_generation"]},
        {"name": "survey-agent", "desc": "Designs and analyzes surveys for research", "caps": ["survey_design", "distribution", "response_analysis", "statistical_reporting"]},
    ],
    "integration": [
        {"name": "hubspot-connector", "desc": "Manages HubSpot CRM integration and data sync", "caps": ["contact_sync", "deal_management", "workflow_triggers", "property_mapping"]},
        {"name": "gmail-connector", "desc": "Manages Gmail SMTP integration for email delivery", "caps": ["email_sending", "template_management", "tracking", "bounce_handling"]},
        {"name": "apollo-connector", "desc": "Manages Apollo.io integration for lead enrichment", "caps": ["people_search", "enrichment", "sequence_management", "data_sync"]},
        {"name": "slack-connector", "desc": "Manages Slack integration for notifications and commands", "caps": ["message_sending", "channel_management", "bot_commands", "webhooks"]},
        {"name": "calendar-connector", "desc": "Manages calendar integration for scheduling", "caps": ["event_creation", "availability_check", "meeting_scheduling", "reminder_management"]},
        {"name": "stripe-connector", "desc": "Manages Stripe integration for payments", "caps": ["payment_processing", "subscription_management", "invoice_generation", "webhook_handling"]},
        {"name": "zapier-connector", "desc": "Manages Zapier integration for workflow automation", "caps": ["zap_creation", "trigger_management", "action_mapping", "error_handling"]},
        {"name": "webhook-receiver", "desc": "Receives and processes incoming webhooks", "caps": ["payload_parsing", "validation", "routing", "acknowledgment"]},
        {"name": "api-gateway", "desc": "Manages API gateway routing and rate limiting", "caps": ["route_management", "rate_limiting", "authentication", "logging"]},
        {"name": "data-transformer", "desc": "Transforms data between different formats and schemas", "caps": ["schema_mapping", "format_conversion", "validation", "enrichment"]},
    ],
    "operations": [
        {"name": "workflow-automator", "desc": "Automates business workflows and processes", "caps": ["workflow_design", "trigger_management", "condition_evaluation", "action_execution"]},
        {"name": "scheduler", "desc": "Manages task scheduling and cron jobs", "caps": ["cron_management", "task_queuing", "priority_scheduling", "retry_logic"]},
        {"name": "notification-manager", "desc": "Manages notifications across all channels", "caps": ["multi_channel", "template_management", "preference_management", "delivery_tracking"]},
        {"name": "inventory-tracker", "desc": "Tracks inventory and resource availability", "caps": ["stock_tracking", "reorder_alerts", "usage_forecasting", "supplier_management"]},
        {"name": "process-monitor", "desc": "Monitors business processes for efficiency", "caps": ["process_mapping", "bottleneck_detection", "optimization_suggestions", "compliance_checking"]},
        {"name": "resource-allocator", "desc": "Allocates resources across teams and projects", "caps": ["capacity_planning", "allocation_optimization", "conflict_resolution", "utilization_tracking"]},
        {"name": "compliance-checker", "desc": "Checks operations for regulatory compliance", "caps": ["regulation_tracking", "audit_preparation", "gap_analysis", "remediation_planning"]},
        {"name": "vendor-manager", "desc": "Manages vendor relationships and procurement", "caps": ["vendor_evaluation", "contract_tracking", "performance_monitoring", "cost_optimization"]},
    ],
    "security": [
        {"name": "threat-detector", "desc": "Detects security threats and anomalies", "caps": ["anomaly_detection", "threat_classification", "alert_generation", "pattern_matching"]},
        {"name": "access-controller", "desc": "Manages access control and permissions", "caps": ["rbac_management", "permission_auditing", "access_review", "policy_enforcement"]},
        {"name": "vulnerability-scanner", "desc": "Scans for vulnerabilities in code and infrastructure", "caps": ["code_scanning", "dependency_audit", "configuration_review", "remediation_guidance"]},
        {"name": "audit-logger", "desc": "Maintains comprehensive audit logs", "caps": ["event_logging", "log_analysis", "compliance_reporting", "retention_management"]},
        {"name": "encryption-manager", "desc": "Manages encryption keys and data protection", "caps": ["key_management", "encryption_policy", "certificate_management", "rotation_scheduling"]},
        {"name": "incident-responder", "desc": "Responds to security incidents and breaches", "caps": ["incident_triage", "containment", "investigation", "recovery_planning"]},
        {"name": "compliance-auditor", "desc": "Audits security compliance with standards", "caps": ["standard_mapping", "gap_analysis", "evidence_collection", "report_generation"]},
        {"name": "data-privacy-agent", "desc": "Manages data privacy and GDPR compliance", "caps": ["data_mapping", "consent_management", "deletion_requests", "privacy_impact"]},
    ],
    "finance": [
        {"name": "invoice-processor", "desc": "Processes and manages invoices", "caps": ["invoice_creation", "payment_tracking", "reminder_sending", "reconciliation"]},
        {"name": "expense-tracker", "desc": "Tracks and categorizes business expenses", "caps": ["expense_categorization", "receipt_processing", "budget_tracking", "reporting"]},
        {"name": "revenue-forecaster", "desc": "Forecasts revenue based on pipeline and trends", "caps": ["forecasting_models", "scenario_analysis", "confidence_intervals", "reporting"]},
        {"name": "budget-manager", "desc": "Manages department and project budgets", "caps": ["budget_creation", "spend_tracking", "variance_analysis", "approval_workflows"]},
        {"name": "payment-processor", "desc": "Processes payments and manages billing", "caps": ["payment_collection", "subscription_billing", "dunning", "refund_management"]},
        {"name": "financial-reporter", "desc": "Generates financial reports and statements", "caps": ["report_generation", "data_aggregation", "compliance_formatting", "distribution"]},
    ],
    "hr": [
        {"name": "recruiter", "desc": "Manages recruitment pipeline and candidate sourcing", "caps": ["job_posting", "candidate_screening", "interview_scheduling", "offer_management"]},
        {"name": "onboarding-coordinator", "desc": "Coordinates employee onboarding processes", "caps": ["checklist_management", "document_collection", "training_scheduling", "access_provisioning"]},
        {"name": "performance-reviewer", "desc": "Manages performance review cycles", "caps": ["review_scheduling", "feedback_collection", "goal_tracking", "report_generation"]},
        {"name": "benefits-admin", "desc": "Administers employee benefits programs", "caps": ["enrollment_management", "plan_comparison", "eligibility_tracking", "provider_coordination"]},
        {"name": "culture-agent", "desc": "Promotes company culture and employee engagement", "caps": ["survey_management", "event_planning", "recognition_programs", "sentiment_tracking"]},
    ],
    "legal": [
        {"name": "contract-reviewer", "desc": "Reviews contracts for risk and compliance", "caps": ["clause_analysis", "risk_identification", "redline_suggestions", "compliance_check"]},
        {"name": "terms-generator", "desc": "Generates terms of service and privacy policies", "caps": ["policy_generation", "jurisdiction_compliance", "version_management", "plain_language"]},
        {"name": "ip-manager", "desc": "Manages intellectual property portfolio", "caps": ["trademark_monitoring", "patent_tracking", "license_management", "infringement_detection"]},
        {"name": "dispute-tracker", "desc": "Tracks and manages legal disputes and claims", "caps": ["case_management", "deadline_tracking", "document_management", "status_reporting"]},
        {"name": "regulatory-monitor", "desc": "Monitors regulatory changes and requirements", "caps": ["regulation_tracking", "impact_analysis", "compliance_mapping", "alert_management"]},
    ],
    "product": [
        {"name": "feature-prioritizer", "desc": "Prioritizes features using data-driven frameworks", "caps": ["scoring_models", "impact_estimation", "effort_estimation", "roadmap_planning"]},
        {"name": "roadmap-planner", "desc": "Plans and maintains product roadmaps", "caps": ["timeline_planning", "dependency_mapping", "milestone_tracking", "stakeholder_communication"]},
        {"name": "user-story-writer", "desc": "Writes user stories and acceptance criteria", "caps": ["story_writing", "criteria_definition", "estimation", "dependency_identification"]},
        {"name": "feedback-analyzer", "desc": "Analyzes product feedback for actionable insights", "caps": ["sentiment_analysis", "theme_extraction", "prioritization", "trend_tracking"]},
        {"name": "competitor-watcher", "desc": "Monitors competitor product changes and launches", "caps": ["feature_tracking", "pricing_monitoring", "launch_detection", "gap_analysis"]},
        {"name": "ux-researcher", "desc": "Conducts UX research and usability testing", "caps": ["user_testing", "heuristic_evaluation", "journey_mapping", "recommendation"]},
    ],
    "devops": [
        {"name": "deployment-agent", "desc": "Manages deployments and release processes", "caps": ["ci_cd", "rollback", "blue_green", "canary_releases"]},
        {"name": "monitoring-agent", "desc": "Monitors infrastructure and application health", "caps": ["health_checks", "alerting", "metric_collection", "incident_creation"]},
        {"name": "infrastructure-agent", "desc": "Manages cloud infrastructure provisioning", "caps": ["provisioning", "scaling", "cost_optimization", "configuration"]},
        {"name": "backup-agent", "desc": "Manages data backups and disaster recovery", "caps": ["backup_scheduling", "restoration_testing", "retention_management", "dr_planning"]},
        {"name": "log-analyzer", "desc": "Analyzes logs for errors and patterns", "caps": ["log_parsing", "pattern_detection", "error_correlation", "alert_generation"]},
        {"name": "scaling-agent", "desc": "Manages auto-scaling policies and resources", "caps": ["load_monitoring", "scaling_rules", "cost_awareness", "performance_targets"]},
    ],
    "quality": [
        {"name": "qa-automator", "desc": "Automates quality assurance testing", "caps": ["test_automation", "regression_testing", "smoke_testing", "test_reporting"]},
        {"name": "bug-triager", "desc": "Triages and prioritizes bug reports", "caps": ["severity_classification", "assignment", "duplicate_detection", "impact_analysis"]},
        {"name": "regression-tester", "desc": "Runs regression test suites and reports results", "caps": ["suite_execution", "result_analysis", "flaky_detection", "coverage_reporting"]},
        {"name": "load-tester", "desc": "Performs load and stress testing", "caps": ["scenario_design", "load_generation", "performance_measurement", "bottleneck_identification"]},
    ],
    "data": [
        {"name": "etl-agent", "desc": "Manages ETL pipelines for data processing", "caps": ["extraction", "transformation", "loading", "scheduling"]},
        {"name": "data-cleaner", "desc": "Cleans and normalizes data across sources", "caps": ["deduplication", "normalization", "validation", "enrichment"]},
        {"name": "data-catalog-agent", "desc": "Maintains data catalog and metadata", "caps": ["cataloging", "lineage_tracking", "quality_scoring", "discovery"]},
        {"name": "data-quality-agent", "desc": "Monitors and enforces data quality standards", "caps": ["quality_rules", "anomaly_detection", "profiling", "remediation"]},
        {"name": "embedding-agent", "desc": "Generates and manages vector embeddings", "caps": ["embedding_generation", "index_management", "similarity_search", "model_selection"]},
        {"name": "migration-planner", "desc": "Plans and executes data migrations", "caps": ["schema_mapping", "migration_scripts", "validation", "rollback_planning"]},
    ],
}


def generate_agent_yaml(domain, agent):
    """Generate a YAML agent definition."""
    return {
        "name": agent["name"],
        "domain": domain,
        "type": "agent",
        "version": "1.0.0",
        "description": agent["desc"],
        "capabilities": agent["caps"],
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "temperature": 0.7,
        "execution": {
            "timeout": 300,
            "retry": {"max_attempts": 3, "backoff": "exponential"},
            "concurrency": 1,
        },
        "health_check": {
            "interval": 60,
            "max_failures": 3,
        },
    }


def main():
    total = 0
    for domain, agents in AGENT_DEFINITIONS.items():
        domain_dir = os.path.join(AGENTS_DIR, domain)
        os.makedirs(domain_dir, exist_ok=True)

        for agent in agents:
            config = generate_agent_yaml(domain, agent)
            filepath = os.path.join(domain_dir, f"{agent['name']}.yaml")
            with open(filepath, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            total += 1
            print(f"  [{domain}] {agent['name']}")

    print(f"\nGenerated {total} agent definitions across {len(AGENT_DEFINITIONS)} domains")


if __name__ == "__main__":
    main()
