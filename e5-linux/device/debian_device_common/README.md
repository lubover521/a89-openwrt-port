# debian_device_common

Shared debian adaptations and runtime assets.

Used by [sprd-linux-devs/e5-linux](https://github.com/sprd-linux-devs/e5-linux) as a pinned Git submodule at `device/debian_device_common`.

See `profile.json` for identity and the parent `device/manifest.json` for overlay order.
Device firmware, calibration, credentials and generated images belong in the parent `work/` and `out/` directories.

`patches/` contains Debian package source patches, including the Unisoc ModemManager and BlueZ changes reused by OpenWrt. Both builders use this pinned checkout.
