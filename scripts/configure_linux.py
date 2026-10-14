#!/usr/bin/env python3
"""Prepare a per-user Linux service and optionally extract Ubuntu's XEmbed proxy."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--windows-exe', required=True, help='Absolute path visible from Linux, usually /mnt/c/...')
    parser.add_argument('--no-legacy', action='store_true')
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args()
    windows_exe = Path(args.windows_exe)
    if not windows_exe.is_absolute() or not windows_exe.is_file():
        parser.error('Windows executable must exist at an absolute Linux-visible path')
    source = Path(__file__).resolve().parents[1]
    target = Path.home() / '.local/share/wsl-tray-bridge'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('agent.py', 'lifecycle.py'):
        shutil.copy2(source / 'linux' / name, target / name)
    (target / 'host.json').write_text(json.dumps({'windows_exe': str(windows_exe)}, indent=2) + '\n')
    if not args.no_legacy:
        with tempfile.TemporaryDirectory(prefix='wsl-tray-proxy-') as temporary:
            cache = Path(temporary)
            subprocess.run(['apt-get', 'download', 'plasma-workspace'], cwd=cache, check=True)
            package = next(cache.glob('plasma-workspace*.deb'))
            extracted = cache / 'extracted'
            subprocess.run(['dpkg-deb', '-x', str(package), str(extracted)], check=True)
            binary = extracted / 'usr/bin/xembedsniproxy'
            if not binary.is_file():
                raise RuntimeError('This Ubuntu plasma-workspace package does not contain xembedsniproxy')
            shutil.copy2(binary, target / 'xembedsniproxy')
            (target / 'xembedsniproxy').chmod(0o755)
            shutil.copy2(extracted / 'usr/share/doc/plasma-workspace/copyright', target / 'KDE-COPYRIGHT')
            result = subprocess.run(['ldd', str(target / 'xembedsniproxy')], capture_output=True, text=True, check=True)
            if 'not found' in result.stdout:
                raise RuntimeError('Missing legacy proxy dependencies:\n' + result.stdout)
    else:
        # Keep an earlier proxy from silently remaining enabled after --no-legacy.
        proxy = target / 'xembedsniproxy'
        if proxy.exists():
            proxy.rename(target / 'xembedsniproxy.disabled')
    unit = Path.home() / '.config/systemd/user/wsl-tray-bridge.service'
    unit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / 'linux/wsl-tray-bridge.service', unit)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', unit.name], check=True)
    if not args.no_start:
        subprocess.run(['systemctl', '--user', 'start', unit.name], check=True)
    print('Installed Linux bridge:', target)

if __name__ == '__main__':
    main()
