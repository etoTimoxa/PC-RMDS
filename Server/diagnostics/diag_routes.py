"""
Diagnostic API Routes.
Flask endpoints for diagnostics subsystem with DiagnosticsContext to eliminate global state.
Endpoints:
  GET  /api/health                  — Basic health check
  GET  /api/system/health           — Full system health
  GET  /api/system/diagnostics      — Diagnostic events with pagination/filtering
  GET  /api/system/components       — Component status overview
  POST /api/system/recovery         — Trigger recovery (admin protected)
  GET  /api/system/recovery/history — Recovery history (admin protected)
  GET  /api/system/statistics       — Aggregated diagnostics statistics
  GET  /api/system/agents           — All agents status
  GET  /api/system/agent/<id>       — Single agent detail
"""
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from flask import Blueprint, jsonify, request

from .diagnostics_logger import DiagnosticsLogger, Severity, DiagnosticEvent
from .heartbeat import HeartbeatChecker
from .api_checker import APIHealthChecker
from .stream_checker import StreamChecker
from .command_checker import CommandDeliveryChecker
from .recovery_manager import RecoveryManager, RecoveryAction


@dataclass
class DiagnosticsContext:
    """
    Thread-safe container for diagnostics subsystem references.
    Replaces global mutable state in diag_routes module.
    """
    logger: Optional[DiagnosticsLogger] = None
    heartbeat: Optional[HeartbeatChecker] = None
    api_checker: Optional[APIHealthChecker] = None
    stream_checker: Optional[StreamChecker] = None
    command_checker: Optional[CommandDeliveryChecker] = None
    recovery_mgr: Optional[RecoveryManager] = None
    server_start_time: float = 0.0


# Singleton context (set once at init, read-only afterwards)
_ctx = DiagnosticsContext()

diagnostics_bp = Blueprint('diagnostics', __name__)


def init_routes(
    logger: DiagnosticsLogger,
    heartbeat: Optional[HeartbeatChecker] = None,
    api_checker: Optional[APIHealthChecker] = None,
    stream_checker: Optional[StreamChecker] = None,
    command_checker: Optional[CommandDeliveryChecker] = None,
    recovery_mgr: Optional[RecoveryManager] = None,
):
    """Initialize the diagnostics context with component references."""
    _ctx.logger = logger
    _ctx.heartbeat = heartbeat
    _ctx.api_checker = api_checker
    _ctx.stream_checker = stream_checker
    _ctx.command_checker = command_checker
    _ctx.recovery_mgr = recovery_mgr
    _ctx.server_start_time = time.time()


# ─────────────────────────────────────────────
#  Health Endpoints
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/health', methods=['GET'])
def health_check():
    """Basic health check endpoint. Returns API server status."""
    if _ctx.api_checker:
        return jsonify(_ctx.api_checker.get_health())
    uptime = time.time() - _ctx.server_start_time
    return jsonify({
        'status': 'ok',
        'service': 'PC-RMDS API Server',
        'uptime': int(uptime),
        'uptime_formatted': _format_uptime(uptime),
    })


@diagnostics_bp.route('/api/system/health', methods=['GET'])
def system_health():
    """Full system health status aggregating all subsystems."""
    health: Dict[str, Any] = {
        'timestamp': time.time(),
        'server_uptime': _format_uptime(time.time() - _ctx.server_start_time),
    }

    if _ctx.api_checker:
        health['api'] = _ctx.api_checker.get_health()
    if _ctx.heartbeat:
        health['heartbeat'] = {
            'agent_count': _ctx.heartbeat.agent_count,
            'agents': _ctx.heartbeat.get_all_status(),
        }
    if _ctx.stream_checker:
        health['streams'] = _ctx.stream_checker.get_all_status()
    if _ctx.command_checker:
        health['commands'] = _ctx.command_checker.get_status()
    if _ctx.recovery_mgr:
        health['recovery'] = _ctx.recovery_mgr.get_status()
    if _ctx.logger:
        health['log_event_count'] = _ctx.logger.event_count

    # Determine overall system health
    all_ok = True
    if _ctx.api_checker:
        if _ctx.api_checker.get_health().get('status') != 'ok':
            all_ok = False
    if _ctx.heartbeat:
        for aid, status in _ctx.heartbeat.get_all_status().items():
            if not status.get('is_online', True):
                all_ok = False
                break

    health['system_status'] = 'healthy' if all_ok else 'degraded'
    return jsonify(health)


# ─────────────────────────────────────────────
#  Diagnostics Events Endpoint
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/diagnostics', methods=['GET'])
def system_diagnostics():
    """
    Diagnostic events with pagination and filtering.
    Query params:
      - n (int, default=100): Number of events to return
      - offset (int, default=0): Pagination offset
      - component (str): Filter by component name
      - severity (str): Filter by severity level (debug/info/warning/error/critical)
      - agent_id (str): Filter by agent ID
    """
    if not _ctx.logger:
        return jsonify({'events': [], 'count': 0, 'total': 0})

    n = request.args.get('n', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    n = min(max(n, 1), 500)  # Cap at 500
    offset = max(offset, 0)

    component = request.args.get('component')
    severity_str = request.args.get('severity')
    agent_id = request.args.get('agent_id')

    severity = None
    if severity_str:
        try:
            severity = Severity(severity_str)
        except ValueError:
            pass

    all_events = _ctx.logger.recent_events(
        n=n + offset, component=component, severity=severity, agent_id=agent_id,
    )
    total = len(all_events)
    events = all_events[offset:offset + n]

    return jsonify({
        'events': events,
        'count': len(events),
        'total': total,
        'filters': {
            'n': n,
            'offset': offset,
            'component': component,
            'severity': severity_str,
            'agent_id': agent_id,
        },
    })


# ─────────────────────────────────────────────
#  Components Endpoint
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/components', methods=['GET'])
def system_components():
    """Status overview of all diagnostic components."""
    components: Dict[str, Any] = {}

    if _ctx.heartbeat:
        components['heartbeat'] = {
            'status': 'running' if _ctx.heartbeat.agent_count > 0 else 'idle',
            'agent_count': _ctx.heartbeat.agent_count,
        }
    if _ctx.api_checker:
        ah = _ctx.api_checker.get_health()
        components['api_health'] = {
            'status': ah.get('status'),
            'database': ah.get('database'),
            'websocket_server': ah.get('websocket_server'),
        }
    if _ctx.stream_checker:
        ss = _ctx.stream_checker.get_all_status()
        broken = sum(1 for s in ss.values() if s.get('screenshot', {}).get('is_broken'))
        components['streams'] = {
            'status': 'running',
            'agent_count': len(ss),
            'broken_count': broken,
        }
    if _ctx.command_checker:
        cs = _ctx.command_checker.get_status()
        components['commands'] = {
            'status': 'running',
            'pending': cs.get('pending_count'),
            'acked_total': cs.get('acked_count'),
            'failed_total': cs.get('failed_count'),
        }
    if _ctx.recovery_mgr:
        rs = _ctx.recovery_mgr.get_status()
        components['recovery_manager'] = {
            'status': 'running',
            'recovering_count': rs.get('recovering_count'),
            'strategies': _ctx.recovery_mgr.get_strategies(),
        }
    if _ctx.logger:
        components['diagnostics_logger'] = {
            'status': 'running',
            'event_count': _ctx.logger.event_count,
        }

    return jsonify({
        'components': components,
        'component_count': len(components),
    })


# ─────────────────────────────────────────────
#  Recovery Endpoint (admin-protected)
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/recovery', methods=['POST'])
def trigger_recovery():
    """
    Trigger recovery for an agent.
    ---
    Admin authorization required. Protected endpoint.
    Internal diagnostics API.

    Request body:
      - agent_id (str, required): Agent to recover
      - strategy (str, optional): Recovery strategy name (default: 'generic_error')
    """
    if not _ctx.recovery_mgr:
        return jsonify({'success': False, 'error': 'Recovery manager not initialized'}), 500

    data = request.get_json(silent=True) or {}
    agent_id = data.get('agent_id')
    if not agent_id:
        return jsonify({'success': False, 'error': 'agent_id is required'}), 400

    strategy_name = data.get('strategy', 'generic_error')
    event = DiagnosticEvent(
        component='api_trigger',
        event=strategy_name,
        severity=Severity.ERROR,
        agent_id=agent_id,
        message=f'Manual recovery triggered (strategy={strategy_name})',
    )

    if _ctx.logger:
        _ctx.logger.log_event(event)

    # Async recovery via asyncio loop
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task in the running loop
            result = asyncio.run_coroutine_threadsafe(
                _ctx.recovery_mgr.on_diagnostic_event(event),
                loop,
            )
            success = result.result(timeout=30)
        else:
            success = loop.run_until_complete(
                _ctx.recovery_mgr.on_diagnostic_event(event)
            )
    except Exception as e:
        if _ctx.logger:
            _ctx.logger.error(
                component='diag_routes', event='recovery_trigger_error',
                agent_id=agent_id, message=f'Recovery trigger failed: {e}',
                exception=e,
            )
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success': success,
        'agent_id': agent_id,
        'strategy': strategy_name,
        'message': 'Recovery initiated' if success else 'Recovery skipped (cooldown/max attempts)',
    })


# ─────────────────────────────────────────────
#  Recovery History Endpoint (admin-protected)
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/recovery/history', methods=['GET'])
def recovery_history():
    """
    Get recovery history with pagination.
    ---
    Admin authorization required. Protected endpoint.
    Internal diagnostics API.

    Query params:
      - agent_id (str, optional): Filter by agent
      - n (int, default=100): Number of records
      - offset (int, default=0): Pagination offset
    """
    if not _ctx.recovery_mgr:
        return jsonify({'history': [], 'count': 0}), 200

    agent_id = request.args.get('agent_id')
    n = request.args.get('n', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    n = min(max(n, 1), 500)
    offset = max(offset, 0)

    history = _ctx.recovery_mgr.get_recovery_history(agent_id)
    total = len(history)
    history_page = history[offset:offset + n]

    return jsonify({
        'history': history_page,
        'count': len(history_page),
        'total': total,
        'agent_id': agent_id,
        'filters': {'n': n, 'offset': offset},
    })


# ─────────────────────────────────────────────
#  Statistics Endpoint
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/statistics', methods=['GET'])
def system_statistics():
    """
    Aggregated diagnostics statistics.
    Returns recovery latency, ACK latency, heartbeat delay,
    success rates, and throughput metrics.
    """
    stats: Dict[str, Any] = {
        'server_uptime': _format_uptime(time.time() - _ctx.server_start_time),
    }

    # Command delivery statistics
    if _ctx.command_checker:
        cmd_metrics = _ctx.command_checker.get_metrics()
        stats['commands'] = cmd_metrics

    # Heartbeat statistics
    if _ctx.heartbeat:
        hb_stats = _ctx.heartbeat.get_all_status()
        agent_count = len(hb_stats)
        online_count = sum(
            1 for s in hb_stats.values() if s.get('is_online', False)
        )
        total_missed = sum(
            s.get('missed_count', 0) for s in hb_stats.values()
        )
        stats['heartbeat'] = {
            'agent_count': agent_count,
            'online_count': online_count,
            'offline_count': agent_count - online_count,
            'total_missed_heartbeats': total_missed,
        }

    # Stream statistics
    if _ctx.stream_checker:
        ss = _ctx.stream_checker.get_all_status()
        broken = sum(
            1 for s in ss.values() if s.get('screenshot', {}).get('is_broken')
        )
        active = sum(
            1 for s in ss.values() if s.get('stream_active', False)
        )
        stats['streams'] = {
            'agent_count': len(ss),
            'active_streams': active,
            'broken_pipelines': broken,
        }

    # Recovery statistics
    if _ctx.recovery_mgr:
        rec_status = _ctx.recovery_mgr.get_status()
        stats['recovery'] = {
            'recovering_count': rec_status.get('recovering_count', 0),
            'strategy_count': len(_ctx.recovery_mgr.get_strategies()),
        }

    # API health status
    if _ctx.api_checker:
        health = _ctx.api_checker.get_health()
        stats['api_health'] = {
            'status': health.get('status'),
            'database_healthy': health.get('database'),
            'websocket_healthy': health.get('websocket_server'),
            'uptime': health.get('uptime'),
        }

    # Event count
    if _ctx.logger:
        stats['total_events'] = _ctx.logger.event_count

    return jsonify(stats)


# ─────────────────────────────────────────────
#  Agents Endpoints
# ─────────────────────────────────────────────


@diagnostics_bp.route('/api/system/agents', methods=['GET'])
def list_agents():
    """List all agents with aggregated status from all subsystems."""
    agents: Dict[str, Any] = {}

    if _ctx.heartbeat:
        for aid, hb in _ctx.heartbeat.get_all_status().items():
            agents[aid] = {'heartbeat': hb}

    if _ctx.stream_checker:
        for aid, st in _ctx.stream_checker.get_all_status().items():
            agents.setdefault(aid, {})['streams'] = st

    if _ctx.recovery_mgr:
        for aid, rec in _ctx.recovery_mgr.get_status().get('agents', {}).items():
            agents.setdefault(aid, {})['recovery'] = rec

    return jsonify({'agents': agents, 'agent_count': len(agents)})


@diagnostics_bp.route('/api/system/agent/<agent_id>', methods=['GET'])
def agent_detail(agent_id: str):
    """Detailed information for a single agent."""
    result: Dict[str, Any] = {'agent_id': agent_id}

    if _ctx.heartbeat:
        hb = _ctx.heartbeat.get_agent_status(agent_id)
        if hb:
            result['heartbeat'] = hb

    if _ctx.stream_checker:
        st = _ctx.stream_checker.get_status(agent_id)
        if st:
            result['streams'] = st

    if _ctx.command_checker:
        cmd = _ctx.command_checker.get_status(agent_id)
        if cmd:
            result['commands'] = cmd

    if _ctx.recovery_mgr:
        rec = _ctx.recovery_mgr.get_status(agent_id)
        if rec:
            result['recovery'] = rec

    if _ctx.logger:
        result['recent_events'] = _ctx.logger.recent_events(
            n=20, agent_id=agent_id
        )

    if not any(k in result for k in ('heartbeat', 'streams', 'commands', 'recovery', 'recent_events')):
        return jsonify({'error': f'Agent {agent_id} not found'}), 404

    return jsonify(result)


# ─────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────


def _format_uptime(seconds: float) -> str:
    """Format seconds into human-readable uptime string."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f'{days}d {hours}h {minutes}m {secs}s'
    if hours:
        return f'{hours}h {minutes}m {secs}s'
    return f'{minutes}m {secs}s'