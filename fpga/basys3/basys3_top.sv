`timescale 1ns/1ps
// Basys 3 top level for the hardware test.
//
// An MMCM turns the board's 100 MHz oscillator into 125 MHz, the clock the
// filter needs for 1 Gb/s at 8 bits per cycle. The whole harness, including
// the UART at 1 Mbaud (125 clocks per bit), runs on that clock.
//
// LEDs: 0 = MMCM locked, 1 = RX FIFO overflowed (should stay off),
//       2-3 = low bits of the result-record count.
module basys3_top (
    input  logic       clk,      // 100 MHz
    input  logic       btnC,     // reset
    input  logic       RsRx,     // from the PC
    output logic       RsTx,     // to the PC
    output logic [3:0] led
);
    logic clk_fb;
    logic clk_fb_buf;
    logic clk_125_unbuf;
    logic clk_125;
    logic locked;

    MMCME2_BASE #(
        .CLKIN1_PERIOD   (10.0),
        .DIVCLK_DIVIDE   (1),
        .CLKFBOUT_MULT_F (10.0),   // VCO 1000 MHz
        .CLKOUT0_DIVIDE_F(8.0)     // 125 MHz
    ) u_mmcm (
        .CLKIN1   (clk),
        .CLKFBIN  (clk_fb_buf),
        .CLKFBOUT (clk_fb),
        .CLKFBOUTB(),
        .CLKOUT0  (clk_125_unbuf),
        .CLKOUT0B (),
        .CLKOUT1  (),
        .CLKOUT1B (),
        .CLKOUT2  (),
        .CLKOUT2B (),
        .CLKOUT3  (),
        .CLKOUT3B (),
        .CLKOUT4  (),
        .CLKOUT5  (),
        .CLKOUT6  (),
        .LOCKED   (locked),
        .PWRDWN   (1'b0),
        .RST      (btnC)
    );

    BUFG u_fb_bufg  (.I(clk_fb),        .O(clk_fb_buf));
    BUFG u_clk_bufg (.I(clk_125_unbuf), .O(clk_125));

    // Hold reset until the MMCM has locked, then release it synchronously.
    logic [3:0] reset_pipe = 4'd0;
    always_ff @(posedge clk_125)
        reset_pipe <= {reset_pipe[2:0], locked};
    wire rst_n = reset_pipe[3];

    logic [15:0] results_sent;
    logic        rx_overflow;

    hw_test_core #(.CLKS_PER_BIT(125)) u_core (
        .clk(clk_125), .rst_n,
        .uart_rx_i(RsRx), .uart_tx_o(RsTx),
        .results_sent, .rx_overflow
    );

    assign led = {results_sent[1:0], rx_overflow, locked};
endmodule
