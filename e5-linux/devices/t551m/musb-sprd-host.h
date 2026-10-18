/* SPDX-License-Identifier: GPL-2.0 */
/* SPRD host DMA glue, adapted from the vendor musb_host.c in
 * https://github.com/strongtz/linux-sprd (Linux 4.14).
 * The backend and completion callbacks already live in sprd_musbhsdma.c.
 */
static bool musb_sprd_rx_program(struct dma_channel *channel,
		struct musb *musb, u8 epnum, struct musb_qh *qh,
		struct urb *urb, u32 offset, size_t len)
{
	struct dma_controller *dma = musb->dma_controller;
	struct musb_hw_ep *ep = &musb->endpoints[epnum];
	u16 csr;
	int ret;

	channel->actual_len = 0;
	qh->segsize = len;
	if (musb->is_multipoint) {
		musb_write_rxfunaddr(musb, epnum, qh->addr_reg);
		musb_write_rxhubaddr(musb, epnum, qh->h_addr_reg);
		musb_write_rxhubport(musb, epnum, qh->h_port_reg);
	} else {
		musb_writeb(musb->mregs, MUSB_FADDR, qh->addr_reg);
	}
	musb_writeb(ep->regs, MUSB_RXTYPE, qh->type_reg);
	musb_writeb(ep->regs, MUSB_RXINTERVAL, qh->intv_reg);
	musb_writew(ep->regs, MUSB_RXMAXP,
		qh->maxpacket | ((qh->hb_mult - 1) << 11));
	csr = musb_readw(ep->regs, MUSB_RXCSR);
	if (qh->type == USB_ENDPOINT_XFER_INT) {
		csr |= MUSB_RXCSR_DISNYET;
		musb_writew(ep->regs, MUSB_RXCSR, csr);
	}

	/* Arm the descriptor before allowing the endpoint to request data. */
	wmb();
	ret = dma->channel_program(channel, qh->maxpacket,
		!(urb->transfer_flags & URB_SHORT_NOT_OK),
		urb->transfer_dma + offset, len);
	if (ret <= 0) {
		if (channel->status == MUSB_DMA_STATUS_BUSY)
			dma->channel_abort(channel);
		dma->channel_release(channel);
		ep->rx_channel = NULL;
		csr &= ~(MUSB_RXCSR_DMAENAB | MUSB_RXCSR_H_AUTOREQ |
			 MUSB_RXCSR_AUTOCLEAR | MUSB_RXCSR_H_REQPKT);
		musb_writew(ep->regs, MUSB_RXCSR, csr);
		csr &= ~MUSB_RXCSR_DMAMODE;
		musb_writew(ep->regs, MUSB_RXCSR, csr);
		return false;
	}
	if (!(csr & (MUSB_RXCSR_RXPKTRDY | MUSB_RXCSR_H_AUTOREQ))) {
		csr |= MUSB_RXCSR_DMAMODE | MUSB_RXCSR_DMAENAB |
			MUSB_RXCSR_AUTOCLEAR | MUSB_RXCSR_H_AUTOREQ |
			MUSB_RXCSR_H_REQPKT;
		musb_writew(ep->regs, MUSB_RXCSR, csr);
	}
	return true;
}

/* Continuation used by the DMA backend for the next isochronous packet. */
static void musb_sprd_rx_next(struct dma_channel *channel,
		struct musb *musb, u8 epnum, struct musb_qh *qh,
		struct urb *urb, u32 offset, size_t len)
{
	if (!musb_sprd_rx_program(channel, musb, epnum, qh, urb, offset, len)) {
		struct musb_hw_ep *ep = &musb->endpoints[epnum];
		u16 csr = musb_readw(ep->regs, MUSB_RXCSR);

		/* Retain the host scheduler's PIO error/fallback path. */
		musb_writew(ep->regs, MUSB_RXCSR, csr | MUSB_RXCSR_H_REQPKT);
	}
}

static void musb_sprd_tx_start(struct musb_hw_ep *ep)
{
	u16 csr = musb_readw(ep->regs, MUSB_TXCSR);

	if (!(csr & MUSB_TXCSR_TXPKTRDY) || !(csr & MUSB_TXCSR_DMAENAB)) {
		csr |= MUSB_TXCSR_MODE | MUSB_TXCSR_AUTOSET |
			MUSB_TXCSR_DMAENAB | MUSB_TXCSR_DMAMODE;
		musb_writew(ep->regs, MUSB_TXCSR, csr);
	}
}
