set INSTANCE_NAME {{name}}
set IP_NAME blk_mem_gen
set VERSION 8.4
set WIDTH {{width}}
set DEPTH {{depth}}

create_ip -name $IP_NAME -vendor xilinx.com -library ip -version $VERSION -module_name $INSTANCE_NAME

set_property -dict [list \
    CONFIG.Memory_Type {Simple_Dual_Port_RAM} \
    CONFIG.Write_Width_A $WIDTH \
    CONFIG.Write_Depth_A $DEPTH \
    CONFIG.Read_Width_A $WIDTH \
    CONFIG.Operating_Mode_A {NO_CHANGE} \
    CONFIG.Write_Width_B $WIDTH \
    CONFIG.Read_Width_B $WIDTH \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {true} \
  ] [get_ips $INSTANCE_NAME]
