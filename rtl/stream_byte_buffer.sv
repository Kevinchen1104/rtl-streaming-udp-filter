`timescale 1ns/1ps
// Two-entry skid buffer for the payload stream.
//
// The output register drives m_*. When the output stalls, one more beat can
// land in the skid register. s_ready is the inverse of a flop, so m_ready never
// reaches s_ready through combinational logic.
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
    output logic       m_error,

    // High when no beat will remain after this clock edge, assuming no new
    // input beat is accepted in this cycle.
    output logic       drained
);
    logic [9:0] out_q;
    logic [9:0] skid_q;
    logic       out_valid_q;
    logic       skid_valid_q;

    wire out_free = !out_valid_q || m_ready;

    assign s_ready = rst_n && !skid_valid_q;
    assign m_valid = rst_n && out_valid_q;
    assign {m_data, m_last, m_error} = out_q;
    assign drained = !skid_valid_q && out_free;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            out_q        <= '0;
            skid_q       <= '0;
            out_valid_q  <= 1'b0;
            skid_valid_q <= 1'b0;
        end else if (out_free) begin
            if (skid_valid_q) begin
                // s_ready is low in this cycle, so no new beat arrives.
                out_q        <= skid_q;
                out_valid_q  <= 1'b1;
                skid_valid_q <= 1'b0;
            end else begin
                out_valid_q <= s_valid;
                if (s_valid)
                    out_q <= {s_data, s_last, s_error};
            end
        end else if (s_valid && !skid_valid_q) begin
            skid_q       <= {s_data, s_last, s_error};
            skid_valid_q <= 1'b1;
        end
    end
endmodule
