#!/usr/bin/env python3
"""
Sherlock v2 end-to-end smoke test.

Hits the live v2 chat/stream endpoint across apps, multi-turn conversations,
and diverse query types. Parses SSE events and validates the agent's behavior.

Usage:
    python backend/tests/sherlock_e2e_smoke.py [--base-url http://localhost:8721]

Requires: TEST_USER_EMAIL and TEST_USER_PASSWORD env vars (or uses defaults below).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('sherlock_e2e')

DEFAULT_BASE = os.getenv('SHERLOCK_E2E_BASE_URL', 'http://localhost:8721')
DEFAULT_EMAIL = os.getenv('TEST_USER_EMAIL', 'admin@tatvacare.in')
DEFAULT_PASSWORD = os.getenv('TEST_USER_PASSWORD', 'admin123')

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SSEEvent:
    event_type: str
    data: dict[str, Any]
    raw: str = ''


@dataclass
class TurnResult:
    """Parsed result of a single chat turn."""
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    entity_recognition: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    content: str = ''
    chart: dict | None = None
    blueprint: dict | None = None
    terminal_status: str | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    events: list[SSEEvent] = field(default_factory=list)
    elapsed_ms: float = 0
    http_status: int = 0


@dataclass
class ConversationResult:
    """Result of a multi-turn conversation."""
    app_id: str
    scenario: str
    turns: list[TurnResult] = field(default_factory=list)
    passed: bool = True
    failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def get_access_token(client: httpx.AsyncClient, base: str, email: str, password: str) -> str:
    resp = await client.post(f'{base}/api/auth/login', json={'email': email, 'password': password})
    if resp.status_code != 200:
        raise RuntimeError(f'Login failed: {resp.status_code} {resp.text}')
    return resp.json()['accessToken']


# ---------------------------------------------------------------------------
# SSE stream parser
# ---------------------------------------------------------------------------

def parse_sse_lines(raw: str) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    current_type = ''
    current_data = ''
    for line in raw.split('\n'):
        if line.startswith('event: '):
            current_type = line[7:].strip()
        elif line.startswith('data: '):
            current_data = line[6:]
        elif line == '' and current_data:
            try:
                parsed = json.loads(current_data)
            except json.JSONDecodeError:
                parsed = {'_raw': current_data}
            events.append(SSEEvent(event_type=current_type, data=parsed, raw=current_data))
            current_type = ''
            current_data = ''
    return events


# ---------------------------------------------------------------------------
# Chat turn executor
# ---------------------------------------------------------------------------

async def execute_turn(
    client: httpx.AsyncClient,
    base: str,
    token: str,
    app_id: str,
    message: str,
    session_id: str | None = None,
    provider: str = 'gemini',
    model: str = 'gemini-3.1-pro-preview',
) -> TurnResult:
    result = TurnResult()
    start = time.monotonic()

    body: dict[str, Any] = {
        'appId': app_id,
        'message': message,
        'provider': provider,
        'model': model,
    }
    if session_id:
        body['sessionId'] = session_id

    try:
        resp = await client.post(
            f'{base}/api/report-builder/v2/chat/stream',
            json=body,
            headers={'Authorization': f'Bearer {token}'},
            timeout=180.0,
        )
        result.http_status = resp.status_code
        if resp.status_code != 200:
            result.error_message = f'HTTP {resp.status_code}: {resp.text[:500]}'
            result.terminal_status = 'http_error'
            result.elapsed_ms = (time.monotonic() - start) * 1000
            return result

        events = parse_sse_lines(resp.text)
        result.events = events

        for evt in events:
            if evt.event_type == 'session':
                result.session_id = evt.data.get('sessionId')
                result.provider = evt.data.get('provider')
                result.model = evt.data.get('model')
            elif evt.event_type == 'entity_recognition':
                result.entity_recognition = evt.data
            elif evt.event_type == 'tool_call_start':
                result.tool_calls.append({
                    'toolCallId': evt.data.get('toolCallId'),
                    'toolName': evt.data.get('toolName'),
                    'state': 'executing',
                })
            elif evt.event_type == 'tool_call_end':
                tc_id = evt.data.get('toolCallId')
                for tc in result.tool_calls:
                    if tc['toolCallId'] == tc_id:
                        tc['state'] = 'completed'
                        tc['summary'] = evt.data.get('summary', '')
                        tc['durationMs'] = evt.data.get('durationMs')
                        break
            elif evt.event_type == 'content_delta':
                result.content += evt.data.get('delta', '')
            elif evt.event_type == 'chart':
                result.chart = evt.data
            elif evt.event_type == 'blueprint':
                result.blueprint = evt.data
            elif evt.event_type == 'done':
                result.terminal_status = evt.data.get('terminalStatus', 'done')
                result.content = evt.data.get('content', result.content)
                result.warnings = evt.data.get('warnings', [])
                # Phase 1: ``done`` event carries opaque artifact triples.
                # Project out the analytics chart payload for smoke-test
                # assertions; other pack artifacts are ignored here.
                for artifact in evt.data.get('artifacts') or []:
                    if not isinstance(artifact, dict):
                        continue
                    if (
                        artifact.get('pack_id') == 'analytics'
                        and artifact.get('contract_id') == 'analytics.chart.v1'
                    ):
                        result.chart = artifact.get('payload')
                        break
            elif evt.event_type == 'error':
                result.terminal_status = evt.data.get('terminalStatus', 'error')
                result.error_message = evt.data.get('message', '')

    except httpx.ReadTimeout:
        result.terminal_status = 'timeout'
        result.error_message = 'Read timeout after 180s'
    except Exception as exc:
        result.terminal_status = 'exception'
        result.error_message = str(exc)

    result.elapsed_ms = (time.monotonic() - start) * 1000
    return result


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

SCENARIOS: list[dict[str, Any]] = [
    # --- kaira-bot ---
    {
        'app_id': 'kaira-bot',
        'scenario': 'single_turn_pass_rate',
        'turns': ['What is the overall pass rate?'],
        'checks': ['has_content', 'no_error', 'has_entity_recognition'],
    },
    {
        'app_id': 'kaira-bot',
        'scenario': 'single_turn_failures',
        'turns': ['Summarize the latest evaluation results and highlight any failures'],
        'checks': ['has_content', 'no_error', 'used_data_query'],
    },
    {
        'app_id': 'kaira-bot',
        'scenario': 'multi_turn_drill_down',
        'turns': [
            'Show me the pass rate trend over the last runs',
            'Which evaluators are failing the most?',
            'Show the rules that are most violated',
        ],
        'checks': ['has_content', 'no_error', 'session_preserved'],
    },
    {
        'app_id': 'kaira-bot',
        'scenario': 'off_topic_rejection',
        'turns': ['Who is the prime minister of India?'],
        'checks': ['has_content', 'no_error', 'off_topic_rejected'],
    },
    {
        'app_id': 'kaira-bot',
        'scenario': 'chart_generation',
        'turns': ['Show me pass rate by evaluator as a bar chart'],
        'checks': ['has_content', 'no_error', 'has_chart'],
    },
    {
        'app_id': 'kaira-bot',
        'scenario': 'entity_resolution',
        'turns': ['Show me results for adversarial runs'],
        'checks': ['has_content', 'no_error', 'used_tool'],
    },
    # --- voice-rx ---
    {
        'app_id': 'voice-rx',
        'scenario': 'voice_rx_pass_rate',
        'turns': ['What is the overall pass rate for voice-rx?'],
        'checks': ['has_content', 'no_error'],
    },
    {
        'app_id': 'voice-rx',
        'scenario': 'voice_rx_rule_compliance',
        'turns': ['Which rules have the worst compliance rate?'],
        'checks': ['has_content', 'no_error', 'used_data_query'],
    },
    # --- inside-sales ---
    {
        'app_id': 'inside-sales',
        'scenario': 'inside_sales_overview',
        'turns': ['Give me an overview of recent evaluation results'],
        'checks': ['has_content', 'no_error'],
    },
    {
        'app_id': 'inside-sales',
        'scenario': 'inside_sales_agent_breakdown',
        'turns': ['Show results broken down by agent'],
        'checks': ['has_content', 'no_error', 'used_data_query'],
    },
]


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_turn(turn: TurnResult, checks: list[str], turn_idx: int, prev_turns: list[TurnResult]) -> list[str]:
    failures: list[str] = []

    if 'no_error' in checks:
        if turn.terminal_status in ('error', 'timeout', 'exception', 'http_error'):
            failures.append(f'Turn {turn_idx}: terminal_status={turn.terminal_status}, error={turn.error_message}')
        if turn.http_status != 200:
            failures.append(f'Turn {turn_idx}: HTTP {turn.http_status}')

    if 'has_content' in checks:
        if not turn.content or len(turn.content.strip()) < 10:
            failures.append(f'Turn {turn_idx}: empty or trivial content ({len(turn.content)} chars)')

    if 'has_entity_recognition' in checks:
        if not turn.entity_recognition:
            failures.append(f'Turn {turn_idx}: no entity_recognition event received')

    if 'has_chart' in checks:
        if not turn.chart:
            failures.append(f'Turn {turn_idx}: expected chart but none received')

    if 'used_data_query' in checks:
        tool_names = [tc['toolName'] for tc in turn.tool_calls]
        if 'data_query' not in tool_names:
            failures.append(f'Turn {turn_idx}: expected data_query tool call, got {tool_names}')

    if 'used_tool' in checks:
        if not turn.tool_calls:
            failures.append(f'Turn {turn_idx}: expected at least one tool call, got none')

    if 'off_topic_rejected' in checks:
        er = turn.entity_recognition or {}
        if er.get('is_platform_query', True):
            failures.append(f'Turn {turn_idx}: expected off-topic rejection (is_platform_query=false)')

    if 'session_preserved' in checks and turn_idx > 0:
        prev_session = prev_turns[turn_idx - 1].session_id
        if turn.session_id != prev_session:
            failures.append(f'Turn {turn_idx}: session changed from {prev_session} to {turn.session_id}')

    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_scenario(
    client: httpx.AsyncClient,
    base: str,
    token: str,
    scenario: dict[str, Any],
) -> ConversationResult:
    conv = ConversationResult(app_id=scenario['app_id'], scenario=scenario['scenario'])
    session_id: str | None = None

    for i, message in enumerate(scenario['turns']):
        logger.info('  [%s/%s] Turn %d: %s', scenario['app_id'], scenario['scenario'], i, message[:60])
        turn = await execute_turn(
            client, base, token,
            app_id=scenario['app_id'],
            message=message,
            session_id=session_id,
        )
        conv.turns.append(turn)
        if turn.session_id:
            session_id = turn.session_id

        # Log key info
        tool_names = [tc['toolName'] for tc in turn.tool_calls]
        logger.info(
            '    → %s | %dms | tools=%s | content=%d chars | chart=%s',
            turn.terminal_status, turn.elapsed_ms,
            tool_names or 'none', len(turn.content),
            'yes' if turn.chart else 'no',
        )
        if turn.error_message:
            logger.warning('    ✗ ERROR: %s', turn.error_message[:200])
        if turn.warnings:
            logger.info('    ⚠ warnings: %s', turn.warnings)

    # Run checks on the last turn (or all turns for multi-turn)
    checks = scenario.get('checks', [])
    for i, turn in enumerate(conv.turns):
        turn_failures = check_turn(turn, checks, i, conv.turns)
        conv.failures.extend(turn_failures)

    conv.passed = len(conv.failures) == 0
    return conv


async def main():
    parser = argparse.ArgumentParser(description='Sherlock v2 e2e smoke test')
    parser.add_argument('--base-url', default=DEFAULT_BASE)
    parser.add_argument('--email', default=DEFAULT_EMAIL)
    parser.add_argument('--password', default=DEFAULT_PASSWORD)
    parser.add_argument('--app', default=None, help='Run only scenarios for this app_id')
    parser.add_argument('--scenario', default=None, help='Run only this scenario name')
    args = parser.parse_args()

    async with httpx.AsyncClient() as client:
        logger.info('Logging in to %s...', args.base_url)
        token = await get_access_token(client, args.base_url, args.email, args.password)
        logger.info('Authenticated. Running %d scenarios...', len(SCENARIOS))

        results: list[ConversationResult] = []
        scenarios = SCENARIOS
        if args.app:
            scenarios = [s for s in scenarios if s['app_id'] == args.app]
        if args.scenario:
            scenarios = [s for s in scenarios if s['scenario'] == args.scenario]

        for scenario in scenarios:
            logger.info('━━━ %s / %s ━━━', scenario['app_id'], scenario['scenario'])
            conv = await run_scenario(client, args.base_url, token, scenario)
            results.append(conv)

        # --- Summary ---
        print('\n' + '=' * 80)
        print('SHERLOCK v2 E2E SMOKE TEST RESULTS')
        print('=' * 80)

        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        for r in results:
            status = '✓ PASS' if r.passed else '✗ FAIL'
            turn_count = len(r.turns)
            total_ms = sum(t.elapsed_ms for t in r.turns)
            tool_count = sum(len(t.tool_calls) for t in r.turns)
            chart_count = sum(1 for t in r.turns if t.chart)
            terminal = r.turns[-1].terminal_status if r.turns else 'N/A'

            print(f'\n{status}  {r.app_id}/{r.scenario}')
            print(f'       Turns: {turn_count} | Time: {total_ms:.0f}ms | Tools: {tool_count} | Charts: {chart_count} | Terminal: {terminal}')
            if r.failures:
                for f in r.failures:
                    print(f'       ✗ {f}')

        print(f'\n{"=" * 80}')
        print(f'TOTAL: {len(results)} scenarios | {len(passed)} passed | {len(failed)} failed')
        print('=' * 80)

        # --- Detailed tool usage analysis ---
        print('\n--- Tool Usage Distribution ---')
        tool_freq: dict[str, int] = {}
        for r in results:
            for t in r.turns:
                for tc in t.tool_calls:
                    name = tc['toolName']
                    tool_freq[name] = tool_freq.get(name, 0) + 1
        for name, count in sorted(tool_freq.items(), key=lambda x: -x[1]):
            print(f'  {name}: {count}')

        print('\n--- Timing Distribution ---')
        all_turns = [t for r in results for t in r.turns]
        if all_turns:
            times = [t.elapsed_ms for t in all_turns]
            print(f'  Min: {min(times):.0f}ms | Median: {sorted(times)[len(times)//2]:.0f}ms | Max: {max(times):.0f}ms | Avg: {sum(times)/len(times):.0f}ms')

        print('\n--- SQL Errors (from warnings) ---')
        sql_errors = [(r.app_id, r.scenario, t.warnings) for r in results for t in r.turns if t.warnings]
        if sql_errors:
            for app, scen, warns in sql_errors:
                for w in warns:
                    print(f'  [{app}/{scen}] {w}')
        else:
            print('  None')

        print('\n--- Errors ---')
        errors = [(r.app_id, r.scenario, t.error_message) for r in results for t in r.turns if t.error_message]
        if errors:
            for app, scen, err in errors:
                print(f'  [{app}/{scen}] {err[:200]}')
        else:
            print('  None')

        sys.exit(1 if failed else 0)


if __name__ == '__main__':
    asyncio.run(main())
