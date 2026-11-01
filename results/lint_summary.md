# Lint summary

- Status: `pass`
- Tool: `Verilator 5.053 devel rev v5.052-273-g71c6638cc (mod)`
- Gate exit status: `0`
- Tool exit status: `0`
- Warnings: `0`
- Commands:
  - `verilator --lint-only --Wall --Wno-fatal -DSYNTHESIS -Irtl --top-module udp_packet_filter rtl/stream_byte_buffer.sv rtl/udp_packet_filter.sv`
  - `verilator --lint-only --Wall --Wno-fatal -DSYNTHESIS -Irtl --top-module hw_test_core rtl/stream_byte_buffer.sv rtl/udp_packet_filter.sv fpga/basys3/uart_rx.sv fpga/basys3/uart_tx.sv fpga/basys3/sync_fifo.sv fpga/basys3/bram_fifo.sv fpga/basys3/hw_test_core.sv`

No warnings or errors were emitted.
