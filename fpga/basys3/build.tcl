# Build the Basys 3 hardware-test bitstream.
#   vivado -mode batch -source build.tcl -tclargs <src_dir> <out_dir>
# <src_dir> holds the RTL from rtl/ and fpga/basys3/ in one flat folder.

set src  [file normalize [lindex $argv 0]]
set out  [file normalize [lindex $argv 1]]
set part xc7a35tcpg236-1
file mkdir $out

read_verilog -sv [list \
    [file join $src stream_byte_buffer.sv] \
    [file join $src udp_packet_filter.sv] \
    [file join $src uart_rx.sv] \
    [file join $src uart_tx.sv] \
    [file join $src sync_fifo.sv] \
    [file join $src bram_fifo.sv] \
    [file join $src hw_test_core.sv] \
    [file join $src basys3_top.sv]]
read_xdc [file join $src basys3.xdc]

synth_design -top basys3_top -part $part -include_dirs $src -verilog_define SYNTHESIS
opt_design
place_design
phys_opt_design
route_design

report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hier.rpt]
report_timing_summary -max_paths 5 -file [file join $out timing_summary.rpt]
report_clocks -file [file join $out clocks.rpt]

set setup [get_timing_paths -setup -max_paths 1]
set hold  [get_timing_paths -hold -max_paths 1]
set fp [open [file join $out summary.txt] w]
puts $fp "vivado_version [version -short]"
puts $fp "part $part"
puts $fp "wns_ns [get_property SLACK $setup]"
puts $fp "whs_ns [get_property SLACK $hold]"
puts $fp "critical_clock [get_property NAME [get_property ENDPOINT_CLOCK $setup]]"
close $fp

write_bitstream -force [file join $out basys3_top.bit]
