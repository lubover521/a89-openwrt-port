/* SPDX-License-Identifier: GPL-2.0-only */
/* Bounded, resolution-aware fbdev test; no raw display register writes. */
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/kd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void)
{
    struct fb_var_screeninfo v;
    struct fb_fix_screeninfo f;
    int fd = open("/dev/fb0", O_RDWR), tty, mode = KD_TEXT;
    if (fd < 0 || ioctl(fd, FBIOGET_VSCREENINFO, &v) ||
        ioctl(fd, FBIOGET_FSCREENINFO, &f)) {
        perror("fbdev"); return 1;
    }
    printf("M8 display test: %ux%u bpp=%u stride=%u\n",
           v.xres, v.yres, v.bits_per_pixel, f.line_length);
    if (v.bits_per_pixel != 32 || v.xres > 4096 || v.yres > 4096 ||
        f.line_length < v.xres * 4 || f.line_length > 32768 ||
        v.red.length != 8 || v.green.length != 8 || v.blue.length != 8)
        return 2;
    size_t size = (size_t)f.line_length * v.yres;
    uint8_t *frame = calloc(1, size);
    if (!frame) return 3;
    tty = open("/dev/tty0", O_RDWR);
    if (tty >= 0) {
        ioctl(tty, KDGETMODE, &mode);
        ioctl(tty, KDSETMODE, KD_GRAPHICS);
    }
    ioctl(fd, FBIOBLANK, FB_BLANK_UNBLANK);
    for (unsigned y = 0; y < v.yres; y++) {
        uint32_t *row = (uint32_t *)(frame + y * f.line_length);
        for (unsigned x = 0; x < v.xres; x++) {
            unsigned bar = x * 4 / v.xres;
            unsigned r = bar == 0 || bar == 3 ? 255 : 0;
            unsigned g = bar == 1 || bar == 3 ? 255 : 0;
            unsigned b = bar == 2 || bar == 3 ? 255 : 0;
            if (y > v.yres * 3 / 4)
                r = g = b = ((x / 16 + y / 16) & 1) ? 255 : 0;
            row[x] = (r << v.red.offset) | (g << v.green.offset) |
                     (b << v.blue.offset);
        }
    }
    for (int i = 0; i < 90; i++) {
        if (pwrite(fd, frame, size, 0) != (ssize_t)size) {
            perror("frame write"); break;
        }
        sleep(1);
    }
    if (tty >= 0) { ioctl(tty, KDSETMODE, mode); close(tty); }
    free(frame); close(fd);
    return 0;
}
