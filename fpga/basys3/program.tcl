# Load a bitstream into the Basys 3 over JTAG (volatile; the flash is untouched).
#   vivado -mode batch -source program.tcl -tclargs <bitstream>

set bit [file normalize [lindex $argv 0]]
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set device [lindex [get_hw_devices xc7a35t*] 0]
current_hw_device $device
set_property PROGRAM.FILE $bit $device
program_hw_devices $device
refresh_hw_device $device
puts "DONE: [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $device]"
close_hw_target
disconnect_hw_server
