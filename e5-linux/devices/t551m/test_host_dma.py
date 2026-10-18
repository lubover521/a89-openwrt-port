#!/usr/bin/env python3
"""Execute generated SPRD RX/TX DMA setup against fake registers/backend."""
from pathlib import Path
import subprocess
import sys
import tempfile

base = Path(sys.argv[1]) / 'drivers/usb/musb'
source = (base / 'musb_host.c').read_text()
start = source.index('static bool musb_tx_dma_program(')
tx = source[start:source.index('\n/*\n * Program an HDRC endpoint', start)]
header = (base / 'board-musb-sprd-host.h').read_text()
regs = (base / 'musb_regs.h').read_text()
constants = '\n'.join(line for line in regs.splitlines()
                      if line.startswith('#define MUSB_') and
                      line.split()[1] in {
                          'MUSB_FADDR', 'MUSB_RXTYPE', 'MUSB_RXINTERVAL', 'MUSB_RXMAXP',
                          'MUSB_RXCSR', 'MUSB_TXCSR', 'MUSB_RXCSR_DISNYET',
                          'MUSB_RXCSR_RXPKTRDY', 'MUSB_RXCSR_H_AUTOREQ',
                          'MUSB_RXCSR_DMAMODE', 'MUSB_RXCSR_DMAENAB',
                          'MUSB_RXCSR_AUTOCLEAR', 'MUSB_RXCSR_H_REQPKT',
                          'MUSB_TXCSR_TXPKTRDY', 'MUSB_TXCSR_MODE',
                          'MUSB_TXCSR_AUTOSET', 'MUSB_TXCSR_DMAENAB', 'MUSB_TXCSR_DMAMODE'})
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
#define __iomem
#define USB_ENDPOINT_XFER_INT 3
#define URB_SHORT_NOT_OK 1
#define URB_ZERO_PACKET 2
#define MUSB_DMA_STATUS_BUSY 2
#define MUSB_TXCSR_H_WZC_BITS 0
#define wmb() (++barriers)
struct dma_channel { int status, actual_len; };
struct musb;
struct musb_hw_ep { void *regs; struct musb *musb; struct dma_channel *tx_channel, *rx_channel; };
struct dma_controller {
 int (*channel_program)(struct dma_channel *,u16,u8,uintptr_t,size_t);
 void (*channel_release)(struct dma_channel *);
 int (*channel_abort)(struct dma_channel *);
};
struct musb { bool is_multipoint, sprd; struct dma_controller *dma_controller;
             struct musb_hw_ep endpoints[2]; void *mregs; };
struct musb_qh { unsigned int segsize; u16 maxpacket; u8 addr_reg,h_addr_reg,h_port_reg,type_reg,intv_reg,hb_mult,type; };
struct urb { unsigned int transfer_flags; uintptr_t transfer_dma; };
static int result, programs, releases, aborts, barriers, requests, last_mode;
static uintptr_t last_address; static size_t last_len; static u16 last_packet;
static u8 bank[64], common[64];
static u16 musb_readw(void *p,u32 off) {u16 v;memcpy(&v,(u8 *)p+off,2);return v;}
static void musb_writew(void *p,u32 off,u16 v) {
 if(p==bank && off==MUSB_RXCSR && (v&MUSB_RXCSR_H_REQPKT)) {
  assert(programs>0); requests++;
 }
 memcpy((u8 *)p+off,&v,2);
}
static void musb_writeb(void *p,u32 off,u8 v) {((u8 *)p)[off]=v;}
#define musb_write_rxfunaddr(m,e,v) (common[20]=(v))
#define musb_write_rxhubaddr(m,e,v) (common[21]=(v))
#define musb_write_rxhubport(m,e,v) (common[22]=(v))
static bool musb_dma_sprd(struct musb *m) {return m->sprd;}
#define musb_dma_inventra(m) 0
#define musb_dma_ux500(m) 0
#define is_cppi_enabled(m) 0
#define tusb_dma_omap(m) 0
#define musb_tx_dma_set_mode_mentor(ep,q,len,mode) (*(mode)=0)
#define musb_tx_dma_set_mode_cppi_tusb(ep,u,mode) (*(mode)=0)
static int program(struct dma_channel *c,u16 pkt,u8 mode,uintptr_t addr,size_t len) {
 assert(barriers>0); programs++;
 last_address=addr;last_len=len;last_packet=pkt;last_mode=mode;
 if(result>0)c->status=MUSB_DMA_STATUS_BUSY;
 return result;
}
static void release(struct dma_channel *c) {releases++;c->status=0;}
static int abort_dma(struct dma_channel *c) {aborts++;c->status=0;return 0;}
static struct dma_controller dma={program,release,abort_dma};
static void reset(void) {
 memset(bank,0,sizeof(bank));memset(common,0,sizeof(common));
 programs=releases=aborts=barriers=requests=0;result=1;
}
'''
tests = r'''
int main(void) {
 struct musb m={.sprd=true,.dma_controller=&dma,.mregs=common};
 struct musb_hw_ep *ep=&m.endpoints[1];
 struct dma_channel channel;
 struct musb_qh q={.maxpacket=2,.hb_mult=1,.addr_reg=2,.h_addr_reg=3,
   .h_port_reg=4,.type_reg=0x73,.intv_reg=8,.type=USB_ENDPOINT_XFER_INT};
 struct urb urb={.transfer_dma=0x12340000};
 ep->regs=bank;ep->musb=&m;
 for(int mp=0;mp<2;mp++) for(int short_error=0;short_error<2;short_error++) {
  reset();memset(&channel,0,sizeof(channel));ep->rx_channel=&channel;m.is_multipoint=mp;
  urb.transfer_flags=short_error?URB_SHORT_NOT_OK:0;
  assert(musb_sprd_rx_program(&channel,&m,1,&q,&urb,4,2));
  assert(programs==1 && requests==1 && last_packet==2 && last_len==2);
  assert(last_address==0x12340004 && last_mode==!short_error && q.segsize==2);
  assert(ep->rx_channel==&channel && channel.status==MUSB_DMA_STATUS_BUSY);
  u16 csr=musb_readw(bank,MUSB_RXCSR);
  assert((csr&(MUSB_RXCSR_DMAENAB|MUSB_RXCSR_H_AUTOREQ|MUSB_RXCSR_H_REQPKT))==
         (MUSB_RXCSR_DMAENAB|MUSB_RXCSR_H_AUTOREQ|MUSB_RXCSR_H_REQPKT));
  assert(bank[MUSB_RXTYPE]==0x73 && bank[MUSB_RXINTERVAL]==8);
  if(mp)assert(common[20]==2 && common[21]==3 && common[22]==4);
  else assert(common[MUSB_FADDR]==2);
 }
 /* Preserve an already queued packet; descriptors precede the first token. */
 reset();channel.status=0;ep->rx_channel=&channel;
 musb_writew(bank,MUSB_RXCSR,MUSB_RXCSR_RXPKTRDY|MUSB_RXCSR_DMAENAB);
 assert(musb_sprd_rx_program(&channel,&m,1,&q,&urb,0,2));
 assert(programs==1 && requests==0);
 /* Both zero and negative backend returns are failures, not DMA success. */
 for(int error=0;error>=-1;error--) {
  reset();result=error;channel.status=MUSB_DMA_STATUS_BUSY;ep->rx_channel=&channel;
  musb_writew(bank,MUSB_RXCSR,MUSB_RXCSR_DMAENAB|MUSB_RXCSR_DMAMODE|MUSB_RXCSR_AUTOCLEAR);
  assert(!musb_sprd_rx_program(&channel,&m,1,&q,&urb,0,2));
  assert(releases==1 && aborts==1 && requests==0 && !ep->rx_channel);
  assert(!(musb_readw(bank,MUSB_RXCSR)&(MUSB_RXCSR_DMAENAB|MUSB_RXCSR_DMAMODE|MUSB_RXCSR_AUTOCLEAR)));
  reset();result=error;channel.status=MUSB_DMA_STATUS_BUSY;ep->tx_channel=&channel;
  assert(!musb_tx_dma_program(&dma,ep,&q,&urb,0,512));
  assert(releases==1 && aborts==1 && !ep->tx_channel);
 }
 for(int zlp=0;zlp<2;zlp++) {
  reset();channel.status=0;ep->tx_channel=&channel;urb.transfer_flags=zlp?URB_ZERO_PACKET:0;
  q.maxpacket=512;
  assert(musb_tx_dma_program(&dma,ep,&q,&urb,8,4096));
  assert(programs==1 && last_len==4096 && last_packet==512 && last_mode==zlp);
  assert(last_address==0x12340008 && q.segsize==4096);
  assert((musb_readw(bank,MUSB_TXCSR)&(MUSB_TXCSR_DMAENAB|MUSB_TXCSR_AUTOSET))==
         (MUSB_TXCSR_DMAENAB|MUSB_TXCSR_AUTOSET));
 }
 reset();channel.status=0;ep->rx_channel=&channel;
 musb_sprd_rx_next(&channel,&m,1,&q,&urb,16,512);
 assert(programs==1 && last_address==0x12340010 && requests==1);
 puts("PASS: RX/TX DMA starts, descriptor ordering, addressing, short/ZLP flags, continuation and failed-channel cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix='sprd-host-dma-') as directory:
    root = Path(directory)
    (root / 'test.c').write_text(constants + '\n' + prelude + header + tx + tests)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(root / 'test.c'), '-o', str(root / 'test')], check=True)
    subprocess.run([str(root / 'test')], check=True)
