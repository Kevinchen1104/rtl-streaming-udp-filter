`timescale 1ns/1ps
// 8N1 UART receiver. Samples each bit in the middle; valid pulses for one
// cycle per received byte. A byte with a bad stop bit is dropped.
module uart_rx #(
    parameter int CLKS_PER_BIT = 125
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       rx,
    output logic [7:0] data,
    output logic       valid
);
    localparam int CW = $clog2(CLKS_PER_BIT);

    typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;
    state_t       state;
    logic [CW-1:0] count;
    logic [2:0]   bit_index;
    logic [7:0]   shift;
    logic         rx_meta;
    logic         rx_sync;

    always_ff @(posedge clk) begin
        valid <= 1'b0;
        if (!rst_n) begin
            state     <= IDLE;
            count     <= '0;
            bit_index <= 3'd0;
            shift     <= 8'd0;
            data      <= 8'd0;
            rx_meta   <= 1'b1;
            rx_sync   <= 1'b1;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
            case (state)
                IDLE: begin
                    count <= '0;
                    if (!rx_sync)
                        state <= START;
                end
                START: begin
                    if (count == CW'(CLKS_PER_BIT / 2 - 1)) begin
                        count     <= '0;
                        bit_index <= 3'd0;
                        if (rx_sync)
                            state <= IDLE;  // a glitch, not a start bit
                        else
                            state <= DATA;
                    end else begin
                        count <= count + 1'b1;
                    end
                end
                DATA: begin
                    if (count == CW'(CLKS_PER_BIT - 1)) begin
                        count <= '0;
                        shift <= {rx_sync, shift[7:1]};
                        if (bit_index == 3'd7)
                            state <= STOP;
                        else
                            bit_index <= bit_index + 3'd1;
                    end else begin
                        count <= count + 1'b1;
                    end
                end
                STOP: begin
                    if (count == CW'(CLKS_PER_BIT - 1)) begin
                        state <= IDLE;
                        if (rx_sync) begin
                            data  <= shift;
                            valid <= 1'b1;
                        end
                    end else begin
                        count <= count + 1'b1;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
