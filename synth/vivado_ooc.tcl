# Out-of-context implementation of udp_packet_filter for the Basys 3 FPGA
# (XC7A35T-1CPG236C) at a 125 MHz clock target. Out of context means no I/O
# buffers or pin placement, so timing covers register-to-register paths.
#
# Run through scripts/run_vivado.py, or directly:
#   vivado -mode batch -source synth/vivado_ooc.tcl -tclargs <rtl_dir> <out_dir>

set rtl_dir [file normalize [lindex $argv 0]]
set out_dir [file normalize [lindex $argv 1]]
set part    xc7a35tcpg236-1
set period  8.000

file mkdir $out_dir
set xdc [file join $out_dir clock.xdc]
set fp [open $xdc w]
puts $fp "create_clock -name clk -period $period \[get_ports clk\]"
close $fp

read_verilog -sv [list \
    [file join $rtl_dir stream_byte_buffer.sv] \
    [file join $rtl_dir udp_packet_filter.sv]]
read_xdc -mode out_of_context $xdc

synth_design -top udp_packet_filter -part $part -mode out_of_context \
    -include_dirs $rtl_dir -verilog_define SYNTHESIS
opt_design
place_design
phys_opt_design
route_design

report_utilization -file [file join $out_dir utilization.rpt]
report_timing_summary -max_paths 5 -file [file join $out_dir timing_summary.rpt]
report_timing -max_paths 1 -path_type full -file [file join $out_dir critical_path.rpt]

set setup [get_timing_paths -setup -max_paths 1]
set hold  [get_timing_paths -hold -max_paths 1]
set fp [open [file join $out_dir summary.txt] w]
puts $fp "vivado_version [version -short]"
puts $fp "part $part"
puts $fp "period_ns $period"
puts $fp "wns_ns [get_property SLACK $setup]"
puts $fp "whs_ns [get_property SLACK $hold]"
puts $fp "critical_from [get_property STARTPOINT_PIN $setup]"
puts $fp "critical_to [get_property ENDPOINT_PIN $setup]"
puts $fp "logic_levels [get_property LOGIC_LEVELS $setup]"
close $fp
