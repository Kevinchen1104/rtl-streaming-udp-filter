`timescale 1ns/1ps
module stream_byte_buffer (
    input  logic       clk,
    input  logic       rst_n,

    input  logic [7:0] s_data,
    input  logic       s_valid,
    output logic       s_ready,
    input  logic       s_last,
    input  logic       s_error,

    output logic [7:0] m_data,
    output logic       m_valid,
    input  logic       m_ready,
    output logic       m_last,
    output logic       m_error
);
    logic [7:0] data_q;
    logic       valid_q;
    logic       last_q;
    logic       error_q;

    assign s_ready = rst_n && (!valid_q || m_ready);
    assign m_valid = rst_n && valid_q;
    assign m_data  = data_q;
    assign m_last  = last_q;
    assign m_error = error_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            data_q  <= 8'd0;
            valid_q <= 1'b0;
            last_q  <= 1'b0;
            error_q <= 1'b0;
        end else if (!valid_q || m_ready) begin
            valid_q <= s_valid;
            if (s_valid) begin
                data_q  <= s_data;
                last_q  <= s_last;
                error_q <= s_error;
            end
        end
    end
endmodule
