"""Blufire command-line interface — single entry point for all Phase 1 flows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blufire import __version__
from blufire.logging_setup import configure, get_logger, new_run_id
from blufire.runtime.context import RunContext, TenantContext
from blufire.settings import Settings, get_settings, load_settings


def _ctx(agent: str, settings: Settings) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent=agent, run_id=new_run_id())


def _cmd_leadgen_run(args: argparse.Namespace, settings: Settings) -> int:
    ctx = _ctx("lead_generation", settings)
    if args.scope == "ad-hoc":
        if args.via_capability:
            from blufire.runtime.bootstrap import LEAD_GENERATION_BLUEPRINT, bootstrap
            from blufire.runtime.orchestrators import lead_generation as orchestrator

            bootstrap(settings)
            result = orchestrator.run(
                ctx,
                LEAD_GENERATION_BLUEPRINT,
                job_titles=args.titles or ["CEO", "Owner"],
                location=args.location,
                limit=args.limit,
            )
            ctx.log.info("leadgen_adhoc_done", **result["counters"])
        else:
            from blufire.agents import lead_generation

            results = lead_generation.run(
                ctx,
                job_titles=args.titles or ["CEO", "Owner"],
                location=args.location,
                limit=args.limit,
            )
            ctx.log.info("leadgen_adhoc_done", count=len(results))
    else:
        if args.via_capability:
            from blufire.runtime.bootstrap import DAILY_LEADGEN_BLUEPRINT, bootstrap
            from blufire.runtime.orchestrators import daily_lead_gen as orchestrator

            bootstrap(settings)
            counters = orchestrator.run(ctx, DAILY_LEADGEN_BLUEPRINT)
        else:
            from blufire.agents import daily_lead_gen

            counters = daily_lead_gen.run(ctx)
        ctx.log.info("leadgen_daily_done", **counters)
    return 0


def _cmd_outreach_run(args: argparse.Namespace, settings: Settings) -> int:
    ctx = _ctx("email_outreach", settings)
    if args.via_capability:
        from blufire.runtime.bootstrap import EMAIL_OUTREACH_BLUEPRINT, bootstrap
        from blufire.runtime.orchestrators import email_outreach as orchestrator

        bootstrap(settings)
        counters = orchestrator.run(
            ctx,
            EMAIL_OUTREACH_BLUEPRINT,
            campaign_context=args.campaign,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    else:
        from blufire.agents import email_outreach

        counters = email_outreach.run(
            ctx,
            campaign_context=args.campaign,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    ctx.log.info("outreach_done", **counters)
    return 0


def _cmd_pipeline_run(args: argparse.Namespace, settings: Settings) -> int:
    ctx = _ctx("crm_pipeline", settings)
    if args.via_capability:
        from blufire.runtime.bootstrap import CRM_PIPELINE_BLUEPRINT, bootstrap
        from blufire.runtime.orchestrators import crm_pipeline as orchestrator

        bootstrap(settings)
        result = orchestrator.run(ctx, CRM_PIPELINE_BLUEPRINT, auto_tasks=args.auto_tasks)
    else:
        from blufire.agents import crm_pipeline

        result = crm_pipeline.run(ctx, auto_tasks=args.auto_tasks)
    ctx.log.info("pipeline_done", **{k: v for k, v in result.items() if k != "actions"})
    return 0


def _cmd_suppress(args: argparse.Namespace, settings: Settings) -> int:
    from blufire.compliance.suppression import SuppressionList

    suppression = SuppressionList(settings.suppression_db_path, settings.tenant.id)
    if args.subcommand == "add":
        suppression.add(args.email, reason=args.reason or "manual", source="cli")
        get_logger().info("suppression_added", email_redacted=True)
    elif args.subcommand == "import":
        added = suppression.import_csv(args.path)
        get_logger().info("suppression_imported", rows=added)
    elif args.subcommand == "check":
        status = suppression.is_suppressed(args.email)
        print(f"{'suppressed' if status else 'not-suppressed'}")
    return 0


def _cmd_unsubscribe_server(args: argparse.Namespace, settings: Settings) -> int:
    try:
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "Install the unsubscribe-server extra: pip install 'blufire[unsubscribe-server]'\n"
        )
        return 2

    from blufire.compliance.unsubscribe_server import build_app

    app = build_app(settings)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    """Report config + secret + path readiness without exposing values."""
    log = get_logger("blufire.doctor")
    issues = 0
    for name in ("hubspot_api_key", "anthropic_api_key", "apollo_api_key", "gmail_app_password"):
        if getattr(settings.secrets, name) is None:
            log.error("secret_missing", key=name.upper())
            issues += 1
    if not settings.secrets.gmail_user:
        log.warning("optional_missing", key="GMAIL_USER")
    if settings.compliance.unsubscribe_base_url is None:
        log.warning("optional_missing", key="UNSUBSCRIBE_BASE_URL")
    if not settings.paths.data_dir.exists():
        log.warning("path_missing", path=str(settings.paths.data_dir))
    if not settings.paths.log_dir.exists():
        log.warning("path_missing", path=str(settings.paths.log_dir))
    log.info("doctor_done", issues=issues, tenant_id=settings.tenant.id)
    return 1 if issues else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blufire", description="Blufire autopilot CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Path to config.yaml (overrides env)")
    sub = parser.add_subparsers(dest="command", required=True)

    leadgen = sub.add_parser("leadgen", help="Lead generation").add_subparsers(
        dest="leadgen_cmd", required=True
    )
    leadgen_run = leadgen.add_parser("run", help="Run a lead-gen pass")
    leadgen_run.add_argument(
        "--scope",
        choices=["daily", "ad-hoc"],
        default="daily",
        help="'daily' uses prospect_searches from config; 'ad-hoc' uses --titles/--location",
    )
    leadgen_run.add_argument("--titles", nargs="*", help="Job titles for ad-hoc search")
    leadgen_run.add_argument("--location", help="Location for ad-hoc search")
    leadgen_run.add_argument("--limit", type=int, default=25)
    leadgen_run.add_argument(
        "--via-capability",
        action="store_true",
        help="Run through the Phase 2 ToolRegistry / Capability orchestrator "
        "instead of the Phase 1 module path. Supported on both --scope ad-hoc "
        "and --scope daily.",
    )
    leadgen_run.set_defaults(func=_cmd_leadgen_run)

    outreach = sub.add_parser("outreach", help="Email outreach").add_subparsers(
        dest="outreach_cmd", required=True
    )
    outreach_run = outreach.add_parser("run", help="Send / draft outreach for HubSpot contacts")
    outreach_run.add_argument("--campaign", required=True, help="Campaign context for the LLM")
    outreach_run.add_argument("--limit", type=int, default=10)
    outreach_run.add_argument("--dry-run", action="store_true")
    outreach_run.add_argument(
        "--via-capability",
        action="store_true",
        help="Run through the Phase 2 ToolRegistry / Capability orchestrator "
        "instead of the Phase 1 module path.",
    )
    outreach_run.set_defaults(func=_cmd_outreach_run)

    pipeline = sub.add_parser("pipeline", help="CRM pipeline").add_subparsers(
        dest="pipeline_cmd", required=True
    )
    pipeline_run = pipeline.add_parser("run", help="Analyze the CRM pipeline")
    pipeline_run.add_argument("--auto-tasks", action="store_true")
    pipeline_run.add_argument(
        "--via-capability",
        action="store_true",
        help="Run through the Phase 2 ToolRegistry / Capability orchestrator "
        "instead of the Phase 1 module path.",
    )
    pipeline_run.set_defaults(func=_cmd_pipeline_run)

    suppress = sub.add_parser("suppress", help="Suppression list management").add_subparsers(
        dest="subcommand", required=True
    )
    suppress_add = suppress.add_parser("add", help="Add an email to the suppression list")
    suppress_add.add_argument("email")
    suppress_add.add_argument("--reason", default=None)
    suppress_add.set_defaults(func=_cmd_suppress)
    suppress_import = suppress.add_parser("import", help="Bulk import from CSV")
    suppress_import.add_argument("path")
    suppress_import.set_defaults(func=_cmd_suppress)
    suppress_check = suppress.add_parser("check", help="Check whether an email is suppressed")
    suppress_check.add_argument("email")
    suppress_check.set_defaults(func=_cmd_suppress)

    unsub = sub.add_parser("unsubscribe-server", help="Run the unsubscribe HTTP server")
    unsub.add_argument("--host", default="127.0.0.1")
    unsub.add_argument("--port", type=int, default=8000)
    unsub.set_defaults(func=_cmd_unsubscribe_server)

    doctor = sub.add_parser("doctor", help="Validate config + connectivity (read-only)")
    doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings() if args.config is None else load_settings(Path(args.config))
    configure(settings)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return int(func(args, settings) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        get_logger("blufire.cli").exception("cli_command_failed", error_class=type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
