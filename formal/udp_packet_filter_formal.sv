`default_nettype none
// Formal harness for udp_packet_filter (SymbiYosys, see udp_packet_filter.sby).
//
// All inputs are free except for the rules a well-behaved source must follow:
// start in reset, and hold valid, data, and last while stalled. The asserts
// are the handshake and frame-accounting properties from docs/spec.md.
module udp_packet_filter_formal (
    input wire        clk,
    input wire        rst_n,
    input wire [7:0]  s_axis_tdata,
    input wire        s_axis_tvalid,
    input wire        s_axis_tlast,
    input wire [15:0] cfg_dst_port,
    input wire        cfg_msg_type_enable,
    input wire [7:0]  cfg_msg_type,
    input wire        m_axis_tready,
    input wire        result_ready
);
    wire        s_axis_tready;
    wire [7:0]  m_axis_tdata;
    wire        m_axis_tvalid;
    wire        m_axis_tlast;
    wire        m_axis_tuser_error;
    wire        result_valid;
    wire        result_accept;
    wire [3:0]  result_reason;
    wire [31:0] result_src_ip;
    wire [31:0] result_dst_ip;
    wire [15:0] result_src_port;
    wire [15:0] result_dst_port;
    wire [15:0] result_payload_len;
    wire [31:0] result_sequence;

    udp_packet_filter dut (.*);

    wire input_hs  = s_axis_tvalid && s_axis_tready;
    wire output_hs = m_axis_tvalid && m_axis_tready;
    wire result_hs = result_valid && result_ready;

    wire [148:0] descriptor = {
        result_accept, result_reason, result_src_ip, result_dst_ip,
        result_src_port, result_dst_port, result_payload_len, result_sequence
    };

    reg past_valid = 1'b0;
    reg past_rst_n = 1'b0;
    always @(posedge clk) begin
        past_valid <= 1'b1;
        past_rst_n <= rst_n;
    end

    // A cycle where this and the previous cycle are both out of reset.
    wire running = past_valid && rst_n && past_rst_n;

    // ---- Assumptions: environment rules --------------------------------
    always @(*)
        if (!past_valid)
            assume (!rst_n);

    always @(posedge clk)
        if (running && $past(s_axis_tvalid && !s_axis_tready)) begin
            assume (s_axis_tvalid);
            assume (s_axis_tdata == $past(s_axis_tdata));
            assume (s_axis_tlast == $past(s_axis_tlast));
        end

    // ---- Frame bookkeeping ---------------------------------------------
    // Frames closed by an input handshake minus descriptors taken.
    reg [1:0] open_descriptors;
    // A payload beat with last has been sent for the current frame.
    reg       payload_ended;

    always @(posedge clk)
        if (!rst_n) begin
            open_descriptors <= 2'd0;
            payload_ended    <= 1'b0;
        end else begin
            open_descriptors <= open_descriptors
                                + {1'b0, input_hs && s_axis_tlast}
                                - {1'b0, result_hs};
            if (result_hs)
                payload_ended <= 1'b0;
            else if (output_hs && m_axis_tlast)
                payload_ended <= 1'b1;
        end

    // ---- Assertions -----------------------------------------------------
    always @(*)
        if (!rst_n) begin
            assert (!s_axis_tready);
            assert (!m_axis_tvalid);
            assert (!result_valid);
        end

    always @(*)
        if (past_valid && rst_n) begin
            // One descriptor per closed frame, and a pending descriptor
            // blocks the next frame.
            assert (open_descriptors <= 2'd1);
            if (open_descriptors != 2'd0)
                assert (!input_hs);
            if (result_valid) begin
                assert (open_descriptors == 2'd1);
                // Payload completes before the descriptor appears.
                assert (!m_axis_tvalid);
                assert (result_accept == (result_reason == 4'd0));
            end
            // Error is only ever flagged on a last beat.
            if (m_axis_tvalid && m_axis_tuser_error)
                assert (m_axis_tlast);
            // Nothing follows a frame's last payload beat.
            if (payload_ended)
                assert (!m_axis_tvalid);
        end

    always @(posedge clk)
        if (running) begin
            if ($past(m_axis_tvalid && !m_axis_tready)) begin
                assert (m_axis_tvalid);
                assert (m_axis_tdata == $past(m_axis_tdata));
                assert (m_axis_tlast == $past(m_axis_tlast));
                assert (m_axis_tuser_error == $past(m_axis_tuser_error));
            end
            if ($past(result_valid && !result_ready)) begin
                assert (result_valid);
                assert (descriptor == $past(descriptor));
            end
        end

    // ---- Covers: show the properties above are not vacuous -------------
    reg [2:0] beats;
    always @(posedge clk)
        if (!rst_n || result_hs)
            beats <= 3'd0;
        else if (output_hs && beats != 3'd7)
            beats <= beats + 3'd1;

    always @(*)
        if (past_valid && rst_n) begin
            // An accepted frame with at least two payload beats.
            cover (result_valid && result_accept && beats >= 3'd2);
            // A late-truncated frame: partial payload ending in error.
            cover (output_hs && m_axis_tlast && m_axis_tuser_error);
            // Output stalled while the skid register holds a second beat.
            cover (m_axis_tvalid && !m_axis_tready && !dut.output_buffer.s_ready);
            // A descriptor held by result_ready while a new frame waits.
            cover (result_valid && !result_ready && s_axis_tvalid);
        end
endmodule
`default_nettype wire
