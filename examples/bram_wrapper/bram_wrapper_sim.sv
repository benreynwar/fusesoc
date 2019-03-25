module bram_wrapper #(
  parameter WIDTH=10,
  parameter DEPTH=10
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

  logic [WIDTH-1: 0] datas [DEPTH-1:0];

  always_ff @(posedge clk)
  begin
    if (w_valid) begin
      datas[w_address] <= w_data;
    end
    if (ar_valid) begin
      r_data <= datas[ar_address];
    end
    r_valid <= ar_valid;
    if (reset) begin
      r_valid <= 0;
    end
  end;
   
endmodule;
