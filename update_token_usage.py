#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'token_usage.json'
USER_BIN = Path.home() / '.npm-global' / 'bin'

def command_path(name):
    found = shutil.which(name)
    if found:
        return found
    candidate = USER_BIN / name
    if candidate.exists():
        return str(candidate)
    return name


def run(cmd, timeout=60):
    try:
        env = os.environ.copy()
        env['PATH'] = f"{USER_BIN}:{env.get('PATH', '')}"
        resolved = [command_path(cmd[0]), *cmd[1:]]
        p = subprocess.run(resolved, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 999, '', str(exc)


def iso_from_unix(value):
    if value in (None, ''):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        return None


def claude_status():
    code, out, err = run(['claude', 'auth', 'status'], timeout=30)
    if code != 0:
        code, out, err = run(['npx', '-y', '@anthropic-ai/claude-code', 'auth', 'status'], timeout=60)
    base = {
        'id': 'claude-code',
        'name': 'Claude Code',
        'provider': 'Anthropic',
        'plan': 'Claude subscription',
        'login_status': 'unknown',
        'account': None,
        'subscription_type': None,
        'used_tokens': None,
        'limit_tokens': None,
        'reset_at': None,
        'reset_interval_hours': None,
        'source': 'claude auth status + ccusage when sessions exist',
    }
    if code == 0:
        try:
            data = json.loads(out)
            base.update({
                'login_status': 'logged in' if data.get('loggedIn') else 'logged out',
                'account': data.get('email'),
                'subscription_type': data.get('subscriptionType'),
                'plan': f"{str(data.get('subscriptionType') or 'unknown').title()} subscription",
            })
        except Exception:
            base['login_status'] = 'status parse failed'
    else:
        base['login_status'] = 'not connected'
        base['error'] = (err or out)[-300:]
    # ccusage can provide block-level token accounting once Claude Code has project session logs.
    code, out, err = run(['ccusage', 'blocks', '--active', '--json', '--offline'], timeout=60)
    if code != 0:
        code, out, err = run(['npx', '-y', 'ccusage', 'blocks', '--active', '--json', '--offline'], timeout=120)
    if code == 0:
        try:
            usage = json.loads(out)
            base['local_usage'] = usage
            base['source'] = 'claude auth status + ccusage blocks'
            if not (usage.get('blocks') or []):
                base['ccusage_note'] = 'ccusage is installed and readable, but no completed Claude Code usage blocks exist yet on this machine.'
        except Exception:
            base['ccusage_error'] = 'parse failed'
    else:
        msg = (err or out or '').strip()
        if 'No valid Claude data directories found' in msg:
            base['ccusage_note'] = 'No local Claude Code session usage yet on this machine; run Claude Code tasks to populate ~/.claude/projects.'
        else:
            base['ccusage_note'] = 'Claude local usage unavailable; ccusage could not read Claude Code session logs.'
            base['ccusage_error'] = msg[-500:]
    return base


def codex_status():
    base = {
        'id': 'codex',
        'name': 'Codex',
        'provider': 'OpenAI',
        'plan': 'ChatGPT subscription / Codex CLI',
        'login_status': 'unknown',
        'account': 'ChatGPT auth on this machine',
        'subscription_type': None,
        'used_tokens': None,
        'limit_tokens': None,
        'reset_at': None,
        'reset_interval_hours': None,
        'source': 'codex login status + codex-limit',
    }
    code, out, err = run(['codex', 'login', 'status'], timeout=30)
    status_text = f"{out}\n{err}"
    base['login_status'] = 'logged in' if code == 0 and 'Logged in' in status_text else 'not connected'
    code, out, err = run(['codex-limit', '--json'], timeout=90)
    if code == 0:
        try:
            q = json.loads(out)
            base['subscription_type'] = q.get('planType')
            if q.get('planType'):
                base['plan'] = f"ChatGPT {q.get('planType')} / Codex CLI"
            base['codex_quota'] = q
            primary = q.get('primary') or {}
            secondary = q.get('secondary') or {}
            base['primary_used_percent'] = primary.get('usedPercent')
            base['primary_reset_at'] = iso_from_unix(primary.get('resetsAt'))
            base['primary_window_minutes'] = primary.get('windowDurationMins')
            base['secondary_used_percent'] = secondary.get('usedPercent')
            base['secondary_reset_at'] = iso_from_unix(secondary.get('resetsAt'))
            base['secondary_window_minutes'] = secondary.get('windowDurationMins')
            base['reset_at'] = base.get('primary_reset_at')
            base['reset_interval_hours'] = round((primary.get('windowDurationMins') or 0) / 60, 2) if primary.get('windowDurationMins') else None
        except Exception as exc:
            base['quota_error'] = f'parse failed: {exc}'
    else:
        base['quota_error'] = (err or out)[-500:]
    return base


def main():
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'note': 'Auto-generated. Codex quota comes from codex-limit via Codex app-server JSON-RPC account/rateLimits/read. Claude exact remaining quota is not exposed by auth status; ccusage can read local session token blocks after Claude Code sessions exist, and /usage is available interactively inside Claude Code.',
        'subscriptions': [claude_status(), codex_status()],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
