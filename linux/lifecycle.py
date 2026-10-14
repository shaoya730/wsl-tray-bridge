#!/usr/bin/env python3
"""Linux owns both sides; no persistent Windows->wsl.exe client or poller."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

directory = Path(__file__).resolve().parent
windows_exe = Path(json.loads((directory / 'host.json').read_text(encoding='utf-8-sig'))['windows_exe'])
stopping = False

def stop(signum, frame):
    global stopping
    stopping = True

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def finish(process, timeout):
    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

def main():
    windows = agent = None
    env = os.environ.copy()
    # WSL's init-level interop endpoint survives individual terminal sessions.
    if Path('/run/WSL/1_interop').exists():
        env['WSL_INTEROP'] = '/run/WSL/1_interop'
    elif not env.get('WSL_INTEROP'):
        sockets = sorted(Path('/run/WSL').glob('*_interop'), key=lambda p: p.stat().st_mtime, reverse=True)
        if sockets:
            env['WSL_INTEROP'] = str(sockets[0])
    if not windows_exe.is_file():
        print('Missing Windows tray executable: ' + str(windows_exe), file=sys.stderr, flush=True)
        return 1
    try:
        for attempt in range(60):
            if stopping:
                return 0
            if Path('/tmp/.X11-unix/X0').exists():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('WSLg display was not ready')
        arguments = [str(windows_exe), '--stdio']
        if env.get('WSL_TRAY_SELF_TEST') == '1':
            arguments.append('--self-test')
        windows = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, env=env)
        agent = subprocess.Popen([sys.executable, '-u', str(directory / 'agent.py')], stdin=windows.stdout, stdout=windows.stdin, stderr=sys.stderr, env=env)
        # Only the two participants own pipe handles, so VM/service loss produces EOF.
        windows.stdout.close()
        windows.stdin.close()
        print('Linux-managed tray started: windows-helper=%d agent=%d' % (windows.pid, agent.pid), flush=True)
        while not stopping and windows.poll() is None and agent.poll() is None:
            time.sleep(0.2)
        if stopping:
            print('Service stopping: closing Linux agent, then Windows tray', flush=True)
            return 0
        if windows.poll() == 0:
            print('Windows tray exited normally', flush=True)
            return 0
        print('A bridge participant stopped unexpectedly', file=sys.stderr, flush=True)
        return 1
    finally:
        if agent is not None and agent.poll() is None:
            agent.terminate()
        finish(agent, 4)
        # Once the agent closes its stdout, the Windows UI sees EOF and removes its icons.
        finish(windows, 6)

if __name__ == '__main__':
    raise SystemExit(main())
