`timescale 1ns/1ps
// Hardware test harness: feeds udp_packet_filter from a UART and reports its
// output back over the UART. The byte protocol is described in
// sim/hw_protocol.py, which the host side also uses.
//
// A frame command is buffered completely before it is streamed into the
// filter, so the filter sees back-to-back bytes at the full clock rate. Payload
// beats and result records are sent back as tagged bytes. A per-frame stall
// level makes m_axis_tready and result_ready drop at random, so the filter's
// backpressure paths run on silicon too.
module hw_test_core #(
    parameter int CLKS_PER_BIT  = 125,
    parameter int RX_FIFO_DEPTH = 4096,
    parameter int TX_FIFO_DEPTH = 64
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        uart_rx_i,
    output logic        uart_tx_o,
    output logic [15:0] results_sent,
    output logic        rx_overflow
);
    localparam logic [7:0] CMD_FRAME  = 8'hA5;
    localparam logic [7:0] CMD_RESET  = 8'hA6;
    localparam logic [7:0] RSP_RESET  = 8'hAC;
    localparam logic [7:0] TAG_BEAT   = 8'hB0;  // | {last, error}
    localparam logic [7:0] TAG_RESULT = 8'hC0;
    localparam int RESULT_BYTES = 20;

    // ---- UART receive into the RX FIFO ---------------------------------
    logic [7:0] rx_byte;
    logic       rx_valid;
    logic [7:0] rxf_data;
    logic       rxf_full;
    logic       rxf_empty;
    logic       rxf_pop;
    logic [$clog2(RX_FIFO_DEPTH):0] rxf_count;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_uart_rx (
        .clk, .rst_n, .rx(uart_rx_i), .data(rx_byte), .valid(rx_valid)
    );

    bram_fifo #(.WIDTH(8), .DEPTH(RX_FIFO_DEPTH)) u_rx_fifo (
        .clk, .rst_n,
        .wr_data(rx_byte), .wr_en(rx_valid), .full(rxf_full),
        .rd_data(rxf_data), .rd_en(rxf_pop), .empty(rxf_empty), .count(rxf_count)
    );

    always_ff @(posedge clk)
        if (!rst_n)
            rx_overflow <= 1'b0;
        else if (rx_valid && rxf_full)
            rx_overflow <= 1'b1;

    // ---- Command parser -------------------------------------------------
    typedef enum logic [3:0] {
        C_IDLE, C_PORT_HI, C_PORT_LO, C_MSG_EN, C_MSG, C_STALL,
        C_LEN_HI, C_LEN_LO, C_WAIT, C_STREAM, C_RESET
    } cmd_state_t;

    cmd_state_t  cmd;
    logic [15:0] cfg_dst_port;
    logic        cfg_msg_type_enable;
    logic [7:0]  cfg_msg_type;
    logic [7:0]  stall_level;
    logic [15:0] frame_len;
    logic [15:0] remaining;
    logic [4:0]  reset_timer;
    logic        ack_pending;
    logic        ack_sent;
    logic        pipe_ready;

    wire reading_header = (cmd != C_WAIT) && (cmd != C_STREAM) && (cmd != C_RESET);
    assign rxf_pop = (reading_header && !rxf_empty) || ((cmd == C_STREAM) && pipe_ready);

    // The filter is reset by the board reset and by a reset command.
    wire filter_rst_n = rst_n && (cmd != C_RESET);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cmd                 <= C_IDLE;
            cfg_dst_port        <= 16'd0;
            cfg_msg_type_enable <= 1'b0;
            cfg_msg_type        <= 8'd0;
            stall_level         <= 8'd0;
            frame_len           <= 16'd0;
            remaining           <= 16'd0;
            reset_timer         <= 5'd0;
            ack_pending         <= 1'b0;
        end else begin
            if (ack_sent)
                ack_pending <= 1'b0;
            case (cmd)
                C_IDLE:
                    if (!rxf_empty) begin
                        if (rxf_data == CMD_FRAME) begin
                            cmd <= C_PORT_HI;
                        end else if (rxf_data == CMD_RESET) begin
                            cmd         <= C_RESET;
                            reset_timer <= 5'd31;
                        end
                        // Any other byte is skipped while looking for a command.
                    end
                C_PORT_HI: if (!rxf_empty) begin cfg_dst_port[15:8] <= rxf_data; cmd <= C_PORT_LO; end
                C_PORT_LO: if (!rxf_empty) begin cfg_dst_port[7:0]  <= rxf_data; cmd <= C_MSG_EN;  end
                C_MSG_EN:  if (!rxf_empty) begin cfg_msg_type_enable <= rxf_data[0]; cmd <= C_MSG; end
                C_MSG:     if (!rxf_empty) begin cfg_msg_type <= rxf_data; cmd <= C_STALL;     end
                C_STALL:   if (!rxf_empty) begin stall_level <= rxf_data; cmd <= C_LEN_HI;     end
                C_LEN_HI:  if (!rxf_empty) begin frame_len[15:8] <= rxf_data; cmd <= C_LEN_LO; end
                C_LEN_LO:  if (!rxf_empty) begin frame_len[7:0]  <= rxf_data; cmd <= C_WAIT;   end
                C_WAIT:
                    if (frame_len == 16'd0) begin
                        cmd <= C_IDLE;
                    end else if (16'(rxf_count) >= frame_len) begin
                        remaining <= frame_len;
                        cmd       <= C_STREAM;
                    end
                C_STREAM:
                    if (pipe_ready) begin
                        remaining <= remaining - 16'd1;
                        if (remaining == 16'd1)
                            cmd <= C_IDLE;
                    end
                C_RESET:
                    if (reset_timer == 5'd0) begin
                        cmd         <= C_IDLE;
                        ack_pending <= 1'b1;
                    end else begin
                        reset_timer <= reset_timer - 5'd1;
                    end
                default: cmd <= C_IDLE;
            endcase
        end
    end

    // ---- Input register slice and the filter ---------------------------
    logic [7:0] s_tdata;
    logic       s_tvalid;
    logic       s_tready;
    logic       s_tlast;
    logic       s_tuser_unused;
    logic       pipe_drained_unused;

    stream_byte_buffer u_input_slice (
        .clk, .rst_n(filter_rst_n),
        .s_data(rxf_data), .s_valid(cmd == C_STREAM), .s_ready(pipe_ready),
        .s_last(remaining == 16'd1), .s_error(1'b0),
        .m_data(s_tdata), .m_valid(s_tvalid), .m_ready(s_tready),
        .m_last(s_tlast), .m_error(s_tuser_unused), .drained(pipe_drained_unused)
    );

    logic [7:0]  m_tdata;
    logic        m_tvalid;
    logic        m_tready;
    logic        m_tlast;
    logic        m_terror;
    logic        result_valid;
    logic        result_ready;
    logic        result_accept;
    logic [3:0]  result_reason;
    logic [31:0] result_src_ip;
    logic [31:0] result_dst_ip;
    logic [15:0] result_src_port;
    logic [15:0] result_dst_port;
    logic [15:0] result_payload_len;
    logic [31:0] result_sequence;

    udp_packet_filter u_filter (
        .clk, .rst_n(filter_rst_n),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid),
        .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .cfg_dst_port, .cfg_msg_type_enable, .cfg_msg_type,
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser_error(m_terror),
        .result_valid, .result_ready, .result_accept, .result_reason,
        .result_src_ip, .result_dst_ip, .result_src_port, .result_dst_port,
        .result_payload_len, .result_sequence
    );

    // ---- Response serializer -------------------------------------------
    typedef enum logic [1:0] {S_IDLE, S_BEAT, S_RESULT} ser_state_t;

    ser_state_t ser;
    logic [7:0]   beat_data;
    logic [159:0] result_shift;
    logic [4:0]   result_left;
    logic [15:0]  lfsr;
    logic [7:0]   txf_wdata;
    logic         txf_push;
    logic         txf_full;
    logic [7:0]   txf_rdata;
    logic         txf_empty;
    logic         txf_pop;
    logic         tx_ready;
    logic [$clog2(TX_FIFO_DEPTH):0] txf_count_unused;

    wire serializer_free = (ser == S_IDLE) && !ack_pending && !txf_full;
    // Random stalls: stall_level 0 never stalls, 255 almost always does.
    assign m_tready     = serializer_free && (lfsr[7:0] >= stall_level);
    assign result_ready = serializer_free && (lfsr[15:8] >= stall_level) && !m_tvalid;

    always_comb begin
        txf_push  = 1'b0;
        txf_wdata = 8'd0;
        ack_sent  = 1'b0;
        case (ser)
            S_IDLE:
                if (!txf_full) begin
                    if (ack_pending) begin
                        txf_push  = 1'b1;
                        txf_wdata = RSP_RESET;
                        ack_sent  = 1'b1;
                    end else if (m_tvalid && m_tready) begin
                        txf_push  = 1'b1;
                        txf_wdata = TAG_BEAT | {6'd0, m_tlast, m_terror};
                    end else if (result_valid && result_ready) begin
                        txf_push  = 1'b1;
                        txf_wdata = TAG_RESULT;
                    end
                end
            S_BEAT:
                if (!txf_full) begin
                    txf_push  = 1'b1;
                    txf_wdata = beat_data;
                end
            S_RESULT:
                if (!txf_full) begin
                    txf_push  = 1'b1;
                    txf_wdata = result_shift[159:152];
                end
            default: ;
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ser          <= S_IDLE;
            beat_data    <= 8'd0;
            result_shift <= '0;
            result_left  <= 5'd0;
            lfsr         <= 16'hACE1;
            results_sent <= 16'd0;
        end else begin
            // 16-bit maximal-length Galois LFSR.
            lfsr <= {1'b0, lfsr[15:1]} ^ (lfsr[0] ? 16'hB400 : 16'h0000);
            case (ser)
                S_IDLE:
                    if (!txf_full && !ack_pending) begin
                        if (m_tvalid && m_tready) begin
                            beat_data <= m_tdata;
                            ser       <= S_BEAT;
                        end else if (result_valid && result_ready) begin
                            result_shift <= {
                                7'd0, result_accept, 4'd0, result_reason,
                                result_src_ip, result_dst_ip,
                                result_src_port, result_dst_port,
                                result_payload_len, result_sequence
                            };
                            result_left  <= 5'(RESULT_BYTES);
                            results_sent <= results_sent + 16'd1;
                            ser          <= S_RESULT;
                        end
                    end
                S_BEAT:
                    if (!txf_full)
                        ser <= S_IDLE;
                S_RESULT:
                    if (!txf_full) begin
                        result_shift <= {result_shift[151:0], 8'd0};
                        result_left  <= result_left - 5'd1;
                        if (result_left == 5'd1)
                            ser <= S_IDLE;
                    end
                default: ser <= S_IDLE;
            endcase
        end
    end

    // ---- TX FIFO and UART transmit -------------------------------------
    sync_fifo #(.WIDTH(8), .DEPTH(TX_FIFO_DEPTH)) u_tx_fifo (
        .clk, .rst_n,
        .wr_data(txf_wdata), .wr_en(txf_push), .full(txf_full),
        .rd_data(txf_rdata), .rd_en(txf_pop), .empty(txf_empty), .count(txf_count_unused)
    );

    assign txf_pop = tx_ready && !txf_empty;

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_uart_tx (
        .clk, .rst_n, .data(txf_rdata), .valid(!txf_empty), .ready(tx_ready), .tx(uart_tx_o)
    );
endmodule
