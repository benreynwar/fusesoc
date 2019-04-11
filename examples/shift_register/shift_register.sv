module shift_register #(
  parameter DEPTH=40,
  parameter WIDTH=10,
  parameter DEPTH_CUTOFF=32
) (
  input clk,
  input reset,
  input i_valid,
  input [WIDTH-1:0] i_data,
  output o_valid,
  output [WIDTH-1:0] o_data
);
   

  logic [$clog2(DEPTH)-1: 0] write_address;
  logic [$clog2(DEPTH)-1: 0] read_address;
  logic [WIDTH-1: 0] datas [DEPTH-1: 0];
  logic [DEPTH-1: 0] valids;
  logic              active;
  logic              ar_valid;

  if (DEPTH == 0) begin
    assign o_valid = i_valid;
    assign o_data = i_data;
  end else if (DEPTH <= DEPTH_CUTOFF) begin
    // Shallow Depth implementation
    always_ff @(posedge clk)
    begin
      if (i_valid) begin
        datas[DEPTH-1] <= i_data;
        valids[DEPTH-1] <= i_valid;
        for (int ii = 0; ii < DEPTH-1; ii=ii+1) begin
          datas[ii] <= datas[ii+1];
          valids[ii] <= valids[ii+1];
        end;
      end;
      if (reset) begin
        valids <= 0;
      end;
    end;
    assign o_data = datas[0];
    assign o_valid = valids[0] & i_valid;
   
  end else begin
    // Deep Depth Implementation
    always_ff @(posedge clk)
    begin
      /* verilator lint_off WIDTH */
      if (i_valid == 1) begin
        if (write_address == DEPTH-1) begin
          write_address <= 0;
        end else begin
          write_address <= write_address + 1;
        end;
        if (read_address == DEPTH-1) begin
          read_address <= 0;
          active <= 1;
        end else begin
          read_address <= read_address + 1;
        end;
      end;
      /* verilator lint_on WIDTH */
      if (reset == 1) begin
        write_address <= 0;
        read_address <= 1;
        active <= 0;
      end;
    end;
    bram_wrapper #(
      .WIDTH(WIDTH),
      .DEPTH(DEPTH)
    ) mem (
      .clk(clk),
      .reset(reset),
      .w_valid(i_valid),
      .w_address(write_address),
      .w_data(i_data),
      .ar_valid(ar_valid),
      .ar_address(read_address),
      .r_valid(o_valid),
      .r_data(o_data)
       );
   assign ar_valid = i_valid & active;

  end;
  
endmodule;
