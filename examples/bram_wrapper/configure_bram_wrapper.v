module bram_wrapper #(
  parameter WIDTH=10,
  parameter DEPTH=10,
  parameter FABRIC="XILINX"
) (
  input 	                clk,
  input                     reset,
  input                     w_valid,
  input [$clog2(DEPTH)-1:0] w_address,
  input [WIDTH-1:0]         w_data,
  input                     ar_valid,
  input [$clog2(DEPTH)-1:0] ar_address,
  output                    r_valid,
  output [WIDTH-1:0]        r_data
);

  always_comb begin
    $display("fusesoc-configure bram_wrapper {\"width\": %d, \"depth\": %d, \"fabric\": \"%s\"}", WIDTH, DEPTH, FABRIC);
  end

endmodule;
