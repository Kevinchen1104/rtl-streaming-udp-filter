`timescale 1ns/1ps
// Single-clock first-word-fall-through FIFO. The memory has no reset and an
// asynchronous read, so Vivado maps it to distributed RAM. DEPTH must be a
// power of two. Writes when full are dropped.
module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 16
) (
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic [WIDTH-1:0]         wr_data,
    input  logic                     wr_en,
    output logic                     full,
    output logic [WIDTH-1:0]         rd_data,
    input  logic                     rd_en,
    output logic                     empty,
    output logic [$clog2(DEPTH):0]   count
);
    localparam int AW = $clog2(DEPTH);

    logic [WIDTH-1:0] mem [DEPTH];
    logic [AW:0]      wr_ptr;
    logic [AW:0]      rd_ptr;

    assign count   = wr_ptr - rd_ptr;
    assign full    = count[AW];  // count never exceeds DEPTH
    assign empty   = (count == '0);
    assign rd_data = mem[rd_ptr[AW-1:0]];

    always_ff @(posedge clk)
        if (wr_en && !full)
            mem[wr_ptr[AW-1:0]] <= wr_data;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
        end else begin
            if (wr_en && !full)
                wr_ptr <= wr_ptr + 1'b1;
            if (rd_en && !empty)
                rd_ptr <= rd_ptr + 1'b1;
        end
    end
endmodule
