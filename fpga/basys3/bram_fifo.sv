`timescale 1ns/1ps
// Single-clock first-word-fall-through FIFO in block RAM.
//
// The memory has a registered read port, which maps to block RAM. The read
// address is the read pointer after this cycle's pop, so rd_data always shows
// the word at the head of the FIFO. A written word becomes visible one cycle
// after the write (empty and count use the write pointer delayed by a cycle),
// which avoids reading an address in the same cycle it is written.
// DEPTH must be a power of two. Writes when full are dropped.
module bram_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4096
) (
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic [WIDTH-1:0]       wr_data,
    input  logic                   wr_en,
    output logic                   full,
    output logic [WIDTH-1:0]       rd_data,
    input  logic                   rd_en,
    output logic                   empty,
    output logic [$clog2(DEPTH):0] count     // words visible to the reader
);
    localparam int AW = $clog2(DEPTH);

    (* ram_style = "block" *) logic [WIDTH-1:0] mem [DEPTH];
    logic [AW:0] wr_ptr;
    logic [AW:0] wr_ptr_visible;
    logic [AW:0] rd_ptr;
    logic [AW:0] stored;

    assign stored = wr_ptr - rd_ptr;
    assign full   = stored[AW];  // stored never exceeds DEPTH
    assign count  = wr_ptr_visible - rd_ptr;
    assign empty  = (count == '0);

    wire         do_read     = rd_en && !empty;
    wire [AW:0]  rd_ptr_next = rd_ptr + {{AW{1'b0}}, do_read};

    always_ff @(posedge clk) begin
        if (wr_en && !full)
            mem[wr_ptr[AW-1:0]] <= wr_data;
        rd_data <= mem[rd_ptr_next[AW-1:0]];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr         <= '0;
            wr_ptr_visible <= '0;
            rd_ptr         <= '0;
        end else begin
            if (wr_en && !full)
                wr_ptr <= wr_ptr + 1'b1;
            wr_ptr_visible <= wr_ptr;
            rd_ptr         <= rd_ptr_next;
        end
    end
endmodule
