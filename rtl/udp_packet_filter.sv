`timescale 1ns/1ps
module udp_packet_filter #(
    parameter int unsigned MAX_LOGICAL_FRAME_BYTES = 2048
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,

    input  logic [15:0] cfg_dst_port,
    input  logic        cfg_msg_type_enable,
    input  logic [7:0]  cfg_msg_type,

    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        m_axis_tuser_error,

    output logic        result_valid,
    input  logic        result_ready,
    output logic        result_accept,
    output logic [3:0]  result_reason,
    output logic [31:0] result_src_ip,
    output logic [31:0] result_dst_ip,
    output logic [15:0] result_src_port,
    output logic [15:0] result_dst_port,
    output logic [15:0] result_payload_len,
    output logic [31:0] result_sequence
);
    `include "rtl/udp_packet_filter_reason_codes.svh"

    typedef enum logic [3:0] {
        ST_IDLE,
        ST_ETH_HEADER,
        ST_IPV4_HEADER,
        ST_UDP_HEADER,
        ST_FIRST_PAYLOAD,
        ST_PASS_PAYLOAD,
        ST_DRAIN,
        ST_WAIT_OUTPUT,
        ST_RESULT_HOLD
    } state_t;

    state_t state;
    logic [15:0] byte_index;
    logic [15:0] payload_received;

    logic [15:0] cfg_dst_port_q;
    logic        cfg_msg_type_enable_q;
    logic [7:0]  cfg_msg_type_q;

    logic [7:0]  field_hi;
    logic [15:0] ip_total_length;
    logic [13:0] fragment_field;
    logic [15:0] udp_length;
    logic [23:0] address_shift;
    logic [3:0]  frame_reason;
    logic [31:0] sequence_counter;

    logic        result_valid_q;
    logic        buffer_s_valid;
    logic        buffer_s_ready;
    logic        buffer_s_last;
    logic        buffer_s_error;

    wire input_handshake = s_axis_tvalid && s_axis_tready;

    assign result_valid = rst_n && result_valid_q;

    stream_byte_buffer output_buffer (
        .clk     (clk),
        .rst_n   (rst_n),
        .s_data  (s_axis_tdata),
        .s_valid (buffer_s_valid),
        .s_ready (buffer_s_ready),
        .s_last  (buffer_s_last),
        .s_error (buffer_s_error),
        .m_data  (m_axis_tdata),
        .m_valid (m_axis_tvalid),
        .m_ready (m_axis_tready),
        .m_last  (m_axis_tlast),
        .m_error (m_axis_tuser_error)
    );

    always_comb begin
        s_axis_tready = 1'b0;
        buffer_s_valid = 1'b0;
        buffer_s_last = 1'b0;
        buffer_s_error = 1'b0;

        if (rst_n) begin
            case (state)
                ST_IDLE,
                ST_ETH_HEADER,
                ST_IPV4_HEADER,
                ST_UDP_HEADER,
                ST_DRAIN: s_axis_tready = 1'b1;

                ST_FIRST_PAYLOAD: begin
                    if (!cfg_msg_type_enable_q ||
                        s_axis_tdata == cfg_msg_type_q) begin
                        s_axis_tready = buffer_s_ready;
                        buffer_s_valid = s_axis_tvalid;
                        buffer_s_last = (result_payload_len == 16'd1) ||
                                        s_axis_tlast;
                        buffer_s_error = s_axis_tlast &&
                                         (result_payload_len > 16'd1);
                    end else begin
                        s_axis_tready = 1'b1;
                    end
                end

                ST_PASS_PAYLOAD: begin
                    s_axis_tready = buffer_s_ready;
                    buffer_s_valid = s_axis_tvalid;
                    buffer_s_last = ((payload_received + 16'd1)
                                     == result_payload_len) || s_axis_tlast;
                    buffer_s_error = s_axis_tlast &&
                                     ((payload_received + 16'd1)
                                      < result_payload_len);
                end

                default: s_axis_tready = 1'b0;
            endcase
        end
    end

    task automatic create_descriptor(input logic [3:0] final_reason);
        begin
            result_reason   <= final_reason;
            result_accept   <= (final_reason == REASON_ACCEPT);
            result_sequence <= sequence_counter;
            sequence_counter <= sequence_counter + 32'd1;
            result_valid_q  <= 1'b1;
            state           <= ST_RESULT_HOLD;
        end
    endtask

    task automatic close_or_wait(input logic [3:0] final_reason);
        begin
            frame_reason <= final_reason;
            if (!m_axis_tvalid || m_axis_tready)
                create_descriptor(final_reason);
            else
                state <= ST_WAIT_OUTPUT;
        end
    endtask

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state                   <= ST_IDLE;
            byte_index              <= 16'd0;
            payload_received        <= 16'd0;
            cfg_dst_port_q          <= 16'd0;
            cfg_msg_type_enable_q   <= 1'b0;
            cfg_msg_type_q          <= 8'd0;
            field_hi                <= 8'd0;
            ip_total_length         <= 16'd0;
            fragment_field          <= 14'd0;
            udp_length              <= 16'd0;
            address_shift           <= 24'd0;
            frame_reason            <= REASON_ACCEPT;
            sequence_counter        <= 32'd0;
            result_valid_q          <= 1'b0;
            result_accept           <= 1'b0;
            result_reason           <= REASON_ACCEPT;
            result_src_ip           <= 32'd0;
            result_dst_ip           <= 32'd0;
            result_src_port         <= 16'd0;
            result_dst_port         <= 16'd0;
            result_payload_len      <= 16'd0;
            result_sequence         <= 32'd0;
        end else begin
            case (state)
                ST_IDLE: begin
                    if (input_handshake) begin
                        cfg_dst_port_q        <= cfg_dst_port;
                        cfg_msg_type_enable_q <= cfg_msg_type_enable;
                        cfg_msg_type_q        <= cfg_msg_type;
                        result_src_ip         <= 32'd0;
                        result_dst_ip         <= 32'd0;
                        result_src_port       <= 16'd0;
                        result_dst_port       <= 16'd0;
                        result_payload_len    <= 16'd0;
                        result_reason         <= REASON_ACCEPT;
                        result_accept         <= 1'b0;
                        frame_reason          <= REASON_ACCEPT;
                        byte_index            <= 16'd1;
                        payload_received      <= 16'd0;
                        address_shift         <= 24'd0;
                        if (s_axis_tlast)
                            create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                        else
                            state <= ST_ETH_HEADER;
                    end
                end

                ST_ETH_HEADER: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        if (byte_index == 16'd12)
                            field_hi <= s_axis_tdata;
                        if (byte_index == 16'd13) begin
                            if ({field_hi, s_axis_tdata} != 16'h0800) begin
                                if (s_axis_tlast)
                                    create_descriptor(REASON_NON_IPV4);
                                else begin
                                    frame_reason <= REASON_NON_IPV4;
                                    state <= ST_DRAIN;
                                end
                            end else if (s_axis_tlast) begin
                                create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                            end else begin
                                state <= ST_IPV4_HEADER;
                            end
                        end else if (s_axis_tlast) begin
                            create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                        end
                    end
                end

                ST_IPV4_HEADER: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        if (s_axis_tlast && byte_index != 16'd14 &&
                            byte_index != 16'd17 && byte_index != 16'd23 &&
                            byte_index != 16'd33)
                            create_descriptor(
                                REASON_BAD_LENGTH_OR_TRUNCATED);
                        case (byte_index)
                            16'd14: begin
                                if (s_axis_tdata[7:4] != 4'd4 ||
                                    s_axis_tdata[3:0] != 4'd5) begin
                                    if (s_axis_tlast)
                                        create_descriptor(REASON_BAD_IPV4_HEADER);
                                    else begin
                                        frame_reason <= REASON_BAD_IPV4_HEADER;
                                        state <= ST_DRAIN;
                                    end
                                end else if (s_axis_tlast) begin
                                    create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                                end
                            end
                            16'd16: field_hi <= s_axis_tdata;
                            16'd17: begin
                                ip_total_length <= {field_hi, s_axis_tdata};
                                if ((32'd14 + {16'd0, field_hi, s_axis_tdata})
                                    > MAX_LOGICAL_FRAME_BYTES) begin
                                    if (s_axis_tlast)
                                        create_descriptor(REASON_FRAME_TOO_LONG);
                                    else begin
                                        frame_reason <= REASON_FRAME_TOO_LONG;
                                        state <= ST_DRAIN;
                                    end
                                end else if (s_axis_tlast) begin
                                    create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                                end
                            end
                            16'd20: field_hi <= s_axis_tdata;
                            16'd21: fragment_field <= {field_hi[5:0],
                                                       s_axis_tdata};
                            16'd23: begin
                                if (s_axis_tdata != 8'd17) begin
                                    if (s_axis_tlast)
                                        create_descriptor(REASON_NON_UDP);
                                    else begin
                                        frame_reason <= REASON_NON_UDP;
                                        state <= ST_DRAIN;
                                    end
                                end else if (fragment_field[13] ||
                                             fragment_field[12:0] != 13'd0) begin
                                    if (s_axis_tlast)
                                        create_descriptor(REASON_FRAGMENTED);
                                    else begin
                                        frame_reason <= REASON_FRAGMENTED;
                                        state <= ST_DRAIN;
                                    end
                                end else if (s_axis_tlast) begin
                                    create_descriptor(REASON_BAD_LENGTH_OR_TRUNCATED);
                                end
                            end
                            16'd26: address_shift <= {16'd0, s_axis_tdata};
                            16'd27,
                            16'd28: address_shift <= {address_shift[15:0],
                                                       s_axis_tdata};
                            16'd29: begin
                                result_src_ip <= {address_shift, s_axis_tdata};
                                address_shift <= 24'd0;
                            end
                            16'd30: address_shift <= {16'd0, s_axis_tdata};
                            16'd31,
                            16'd32: address_shift <= {address_shift[15:0],
                                                       s_axis_tdata};
                            16'd33: begin
                                result_dst_ip <= {address_shift, s_axis_tdata};
                                address_shift <= 24'd0;
                                if (s_axis_tlast)
                                    create_descriptor(
                                        REASON_BAD_LENGTH_OR_TRUNCATED);
                                else
                                    state <= ST_UDP_HEADER;
                            end
                            default: ;
                        endcase
                    end
                end

                ST_UDP_HEADER: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        if (s_axis_tlast && byte_index != 16'd41)
                            create_descriptor(
                                REASON_BAD_LENGTH_OR_TRUNCATED);
                        case (byte_index)
                            16'd34: field_hi <= s_axis_tdata;
                            16'd35: result_src_port <= {field_hi, s_axis_tdata};
                            16'd36: field_hi <= s_axis_tdata;
                            16'd37: result_dst_port <= {field_hi, s_axis_tdata};
                            16'd38: field_hi <= s_axis_tdata;
                            16'd39: udp_length <= {field_hi, s_axis_tdata};
                            16'd41: begin
                                if (ip_total_length < 16'd28 ||
                                    udp_length < 16'd8 ||
                                    udp_length != (ip_total_length - 16'd20)) begin
                                    if (s_axis_tlast)
                                        create_descriptor(
                                            REASON_BAD_LENGTH_OR_TRUNCATED);
                                    else begin
                                        frame_reason <=
                                            REASON_BAD_LENGTH_OR_TRUNCATED;
                                        state <= ST_DRAIN;
                                    end
                                end else begin
                                    result_payload_len <= udp_length - 16'd8;
                                    if ((udp_length > 16'd8) && s_axis_tlast) begin
                                        create_descriptor(
                                            REASON_BAD_LENGTH_OR_TRUNCATED);
                                    end else if (result_dst_port != cfg_dst_port_q) begin
                                        if (s_axis_tlast)
                                            create_descriptor(
                                                REASON_DST_PORT_MISMATCH);
                                        else begin
                                            frame_reason <=
                                                REASON_DST_PORT_MISMATCH;
                                            state <= ST_DRAIN;
                                        end
                                    end else if (udp_length == 16'd8) begin
                                        if (cfg_msg_type_enable_q)
                                            frame_reason <=
                                                REASON_MSG_TYPE_MISMATCH;
                                        else
                                            frame_reason <= REASON_ACCEPT;
                                        if (s_axis_tlast) begin
                                            if (cfg_msg_type_enable_q)
                                                create_descriptor(
                                                    REASON_MSG_TYPE_MISMATCH);
                                            else
                                                create_descriptor(REASON_ACCEPT);
                                        end else begin
                                            state <= ST_DRAIN;
                                        end
                                    end else if (cfg_msg_type_enable_q) begin
                                        state <= ST_FIRST_PAYLOAD;
                                    end else begin
                                        state <= ST_PASS_PAYLOAD;
                                    end
                                end
                            end
                            default: ;
                        endcase
                    end
                end

                ST_FIRST_PAYLOAD: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        payload_received <= 16'd1;
                        if (s_axis_tlast && result_payload_len > 16'd1) begin
                            frame_reason <= REASON_BAD_LENGTH_OR_TRUNCATED;
                            if (s_axis_tdata == cfg_msg_type_q)
                                state <= ST_WAIT_OUTPUT;
                            else
                                create_descriptor(
                                    REASON_BAD_LENGTH_OR_TRUNCATED);
                        end else if (s_axis_tdata != cfg_msg_type_q) begin
                            frame_reason <= REASON_MSG_TYPE_MISMATCH;
                            if (s_axis_tlast)
                                create_descriptor(REASON_MSG_TYPE_MISMATCH);
                            else
                                state <= ST_DRAIN;
                        end else if (s_axis_tlast) begin
                            frame_reason <= REASON_ACCEPT;
                            state <= ST_WAIT_OUTPUT;
                        end else if (result_payload_len == 16'd1) begin
                            frame_reason <= REASON_ACCEPT;
                            state <= ST_DRAIN;
                        end else begin
                            state <= ST_PASS_PAYLOAD;
                        end
                    end
                end

                ST_PASS_PAYLOAD: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        payload_received <= payload_received + 16'd1;
                        if (s_axis_tlast) begin
                            if ((payload_received + 16'd1)
                                < result_payload_len)
                                frame_reason <=
                                    REASON_BAD_LENGTH_OR_TRUNCATED;
                            else
                                frame_reason <= REASON_ACCEPT;
                            state <= ST_WAIT_OUTPUT;
                        end else if ((payload_received + 16'd1)
                                     == result_payload_len) begin
                            frame_reason <= REASON_ACCEPT;
                            state <= ST_DRAIN;
                        end
                    end
                end

                ST_DRAIN: begin
                    if (input_handshake) begin
                        byte_index <= byte_index + 16'd1;
                        if (s_axis_tlast)
                            close_or_wait(frame_reason);
                    end
                end

                ST_WAIT_OUTPUT: begin
                    if (!m_axis_tvalid || m_axis_tready)
                        create_descriptor(frame_reason);
                end

                ST_RESULT_HOLD: begin
                    if (result_valid_q && result_ready) begin
                        result_valid_q <= 1'b0;
                        state <= ST_IDLE;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

`ifndef SYNTHESIS
    udp_packet_filter_sva protocol_checks (
        .clk, .rst_n,
        .m_axis_tdata, .m_axis_tvalid, .m_axis_tready,
        .m_axis_tlast, .m_axis_tuser_error,
        .result_valid, .result_ready, .result_accept, .result_reason,
        .result_src_ip, .result_dst_ip, .result_src_port,
        .result_dst_port, .result_payload_len, .result_sequence
    );
`endif
endmodule
