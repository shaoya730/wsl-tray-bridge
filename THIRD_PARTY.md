# Third-party components

This repository does not include precompiled KDE components.

For optional legacy XEmbed support, the installer downloads the `plasma-workspace` package from the user's configured Ubuntu APT repositories and extracts `usr/bin/xembedsniproxy`. It also copies the package's `usr/share/doc/plasma-workspace/copyright` to the installed helper directory as `KDE-COPYRIGHT`.

The component remains subject to its original KDE copyright and license terms. Refer to the extracted copyright file for the exact version installed.

- [Upstream source](https://invent.kde.org/plasma/plasma-workspace/-/tree/Plasma/5.27/xembed-sni-proxy)
- [Ubuntu source package](https://launchpad.net/ubuntu/+source/plasma-workspace)

The tested environment used Ubuntu package `4:5.27.12-0ubuntu0.1` for ARM64. The installer selects the candidate package for the user's own Ubuntu installation and checks that its required shared libraries are available.
