module bram_wrapper_verilog #(
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

  if (1 == 0) begin: u1
  {% for parameters in all_parameters %}
  end elsif ((WIDTH == {{parameters.width}}) && (DEPTH == {{parameters.depth}})) begin: u1{% if fabric == "xilinx" %}
    match_6_8 xilinx_bram_6_8 (
      .clka(clk),
      .reset(reset),
      .ena(w_valid),
      .wea(w_valid),
      .addra(w_address),
      .dina(w_data),
      .clkb(clk),
      .enb(ar_valid),
      .addrb(r_address),
      .doutb(r_data)
    );{% endif %}{% endfor %}
  end else begin
    always_comb begin
      $display("fusesoc-configure xilinx_bram_wrapper_biggen {\"width\": %d, \"depth\": %d}", WIDTH, DEPTH);
    end
    assign r_data = 0;
  end

  always @(posedge clk) begin
    r_valid <= ar_valid;
    if (reset == 1'b1) begin
      r_valid <= 1'b0;
    end
  end
   
endmodule;
