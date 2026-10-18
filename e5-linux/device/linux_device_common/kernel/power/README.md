# Suspend correctness patches

Imported from [CharlesGool/e5-sleep-kernel, e5-sleep2](https://github.com/CharlesGool/e5-sleep-kernel/tree/52ad641/patches),
2026-10-16. Original project license: GPL-2.0; kernel files retain their SPDX
licenses. Credit: CharlesGool.

- 0001 stops the UMP9620 watchdog across system sleep and rearms it on resume.
- 0002 avoids cancelling DPU writeback work that was never initialized.
- 0004 powers the SPRD GPU down across system suspend and restores it before
  panfrost accesses the hardware on resume.
- 0005 introduces the original-DT camera genpd provider.
- 0006 adapts the last two patches: GPU start failures unwind power, and the
  camera/DCAM/ISP sequencing and three-sample PMU confirmation follow the E5
  stock qogirn6l driver. Clock references and bus failures are handled explicitly.
  The camera provider is built in, matching only `sprd,qogirl6l-camsys-domain`;
  it does not claim other camera-domain compatibles.

These patches do not initiate suspend, change hotspot policy, disable IPv6,
change polling intervals, or keep eMMC awake. They only affect the corresponding
drivers and compatible devices. CPU idle is enabled separately in the shared
kernel configuration, consistent with the stock E5/T551M/M8 configuration.

The full stack is covered by transition/failure tests and kernel compilation.
It is not a claim of measured battery-life improvement or whole-system deep
sleep validation on all three models. User field tests remain separate.
