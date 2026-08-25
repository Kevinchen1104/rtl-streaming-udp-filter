`timescale 1ns/1ps
module udp_packet_filter_sva (
    input logic        clk,
    input logic        rst_n,
    input logic [7:0]  m_axis_tdata,
    input logic        m_axis_tvalid,
    input logic        m_axis_tready,
    input logic        m_axis_tlast,
    input logic        m_axis_tuser_error,
    input logic        result_valid,
    input logic        result_ready,
    input logic        result_accept,
    input logic [3:0]  result_reason,
    input logic [31:0] result_src_ip,
    input logic [31:0] result_dst_ip,
    input logic [15:0] result_src_port,
    input logic [15:0] result_dst_port,
    input logic [15:0] result_payload_len,
    input logic [31:0] result_sequence
);
    logic       prior_out_stall;
    logic [9:0] prior_out_bundle;
    logic       prior_result_stall;
    logic [148:0] prior_result_bundle;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            prior_out_stall    <= 1'b0;
            prior_out_bundle   <= '0;
            prior_result_stall <= 1'b0;
            prior_result_bundle <= '0;
        end else begin
            if (prior_out_stall) begin
                assert (m_axis_tvalid)
                    else $error("payload valid dropped while stalled");
                assert ({m_axis_tdata, m_axis_tlast, m_axis_tuser_error}
                        == prior_out_bundle)
                    else $error("payload fields changed while stalled");
            end
            if (prior_result_stall) begin
                assert (result_valid)
                    else $error("result valid dropped while stalled");
                assert ({result_accept, result_reason, result_src_ip,
                         result_dst_ip, result_src_port, result_dst_port,
                         result_payload_len, result_sequence}
                        == prior_result_bundle)
                    else $error("result fields changed while stalled");
            end
            if (result_valid) begin
                assert (result_accept == (result_reason == 4'd0))
                    else $error("accept/reason invariant violated");
                assert (!m_axis_tvalid)
                    else $error("descriptor visible while payload remains pending");
            end

            prior_out_stall  <= m_axis_tvalid && !m_axis_tready;
            prior_out_bundle <= {m_axis_tdata, m_axis_tlast,
                                 m_axis_tuser_error};
            prior_result_stall <= result_valid && !result_ready;
            prior_result_bundle <= {result_accept, result_reason,
                                    result_src_ip, result_dst_ip,
                                    result_src_port, result_dst_port,
                                    result_payload_len, result_sequence};
        end
    end
endmodule
