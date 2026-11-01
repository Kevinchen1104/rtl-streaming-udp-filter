`timescale 1ns/1ps
// 8N1 UART transmitter. A byte is taken when valid and ready are both high.
module uart_tx #(
    parameter int CLKS_PER_BIT = 125
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] data,
    input  logic       valid,
    output logic       ready,
    output logic       tx
);
    localparam int CW = $clog2(CLKS_PER_BIT);

    logic [9:0]    shift;      // stop bit, data LSB first, start bit
    logic [3:0]    bits_left;
    logic [CW-1:0] count;

    assign ready = (bits_left == 4'd0);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            shift     <= '1;
            bits_left <= 4'd0;
            count     <= '0;
            tx        <= 1'b1;
        end else begin
            if (bits_left == 4'd0) begin
                if (valid) begin
                    shift     <= {1'b1, data, 1'b0};
                    bits_left <= 4'd10;
                    count     <= '0;
                end
            end else if (count == CW'(CLKS_PER_BIT - 1)) begin
                count     <= '0;
                shift     <= {1'b1, shift[9:1]};
                bits_left <= bits_left - 4'd1;
            end else begin
                count <= count + 1'b1;
            end
            // Registered output so the line never glitches.
            tx <= (bits_left == 4'd0) ? 1'b1 : shift[0];
        end
    end
endmodule
