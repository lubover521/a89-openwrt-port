# Sourced only after the selected userdata root fails to mount. Never called
# for TF roots or the early read-only firmware/boot-choice probes.
f2fs_repair_userdata() {
    local dev=$1 node=${1##*/} rc before=/run/f2fs-before.log after=/run/f2fs-after.log
    [ -b "$dev" ] || return 1
    grep -qx PARTNAME=userdata "/sys/class/block/$node/uevent" || return 1
    # Compare device numbers too: a mounted alias is still the same device.
    local number
    number=$(cat "/sys/class/block/$node/dev") || return 1
    awk -v n="$number" '$3 == n { found=1 } END { exit !found }' /proc/self/mountinfo && return 1
    [ -z "$(ls -A "/sys/class/block/$node/holders")" ] || return 1
    [ "$(blockdev --getro "$dev")" = 0 ] || return 1
    local magic
    magic=$(od -An -tx4 -j 1024 -N 4 "$dev" | tr -d ' \n')
    [ "$magic" = f2f52010 ] || return 1
    [ -x /repair/lib/ld-musl-aarch64.so.1 ] && [ -x /repair/sbin/fsck.f2fs ] || return 1
    mkdir /run/f2fs-repair.attempted 2>/dev/null || return 1
    touch /run/f2fs-repair.running
    log "stage=f2fs-check dev=$dev reason=userdata-mount-failed"
    # No timeout/reboot may interrupt an active metadata repair. The boot
    # watchdog waits for the running marker; no normal boot delay is added.
    blockdev --setro "$dev" || { rm -f /run/f2fs-repair.running; return 1; }
    # f2fs-tools 1.16 asks to export orphan nodes into ./lost_found even
    # with -f/--dry-run (and -y). EOF asserts instead of returning a check
    # result. Decline that optional host-directory dump, not metadata repair.
    # Supply one answer only; unexpected further prompts must still fail closed.
    printf 'n\n' | /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib \
        /repair/sbin/fsck.f2fs -f --dry-run "$dev" >"$before" 2>&1
    rc=$?
    blockdev --setrw "$dev" || { rm -f /run/f2fs-repair.running; return 1; }
    log "stage=f2fs-check-result rc=$rc"
    # 1 (simulated correction) / 4 (uncorrected errors) only. Operational
    # errors, unknown features, I/O failures, and a clean check are not a
    # reason to write metadata. Never format, resize or touch another partition.
    case "$rc" in 1|4) ;; *) rm -f /run/f2fs-repair.running; return 1 ;; esac
    log "stage=f2fs-repair dev=$dev"
    printf 'n\n' | /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib \
        /repair/sbin/fsck.f2fs -f "$dev" >/run/f2fs-repair.log 2>&1
    rc=$?
    log "stage=f2fs-repair-result rc=$rc"
    case "$rc" in 0|1) ;; *) rm -f /run/f2fs-repair.running; return 1 ;; esac
    blockdev --setro "$dev" || { rm -f /run/f2fs-repair.running; return 1; }
    printf 'n\n' | /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib \
        /repair/sbin/fsck.f2fs -f --dry-run "$dev" >"$after" 2>&1
    rc=$?
    blockdev --setrw "$dev" || { rm -f /run/f2fs-repair.running; return 1; }
    rm -f /run/f2fs-repair.running
    log "stage=f2fs-verify-result rc=$rc"
    [ "$rc" = 0 ] && ! grep -qE '\[Fail\]|ASSERT' "$after"
}
