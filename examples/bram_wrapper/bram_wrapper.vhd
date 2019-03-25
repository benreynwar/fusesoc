library ieee;

use ieee.std_logic_1164.all;
use work.logceil.all;

entity bram_wrapper_vhdl is
  generic (
    WIDTH: positive;
    DEPTH: positive
    );
  port (
    clk: in std_logic;
    reset: in std_logic;
    w_valid: in std_logic;
    w_address: in std_logic_vector(logceil(DEPTH)-1 downto 0);
    w_data: in std_logic_vector(WIDTH-1 downto 0);
    ar_valid: in std_logic;
    ar_address: in std_logic_vector(logceil(DEPTH)-1 downto 0);
    r_valid: out std_logic;
    r_data: out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;

architecture arch of bram_wrapper_vhdl is
begin
  {% for parameters in all_parameters %}
  match_{{parameters.width}}_{{parameters.depth}}: if ((WIDTH={{parameters.width}}) and (DEPTH={{parameters.depth}})) generate
  {% if fabric == "xilinx" %}mem_{{parameters.width}}_{{parameters.depth}}: entity work.{{parameters.name}}
    port map (
      clka => clk,
      ena => w_valid,
      wea => w_valid,
      addra => w_address,
      dina => w_data,
      clkb => clk,
      enb => ar_valid,
      addrb => r_address,
      doutb => r_data
      );
  {% endif %}end generate;{% endfor %}

  nomatch: if not (false{% for parameters in all_parameters %}
                   or ((WIDTH={{parameters.width}}) and (DEPTH={{parameters.depth}})){% endfor %}) generate
    assert false report "fusesoc-configure xilinx_bram_wrapper_biggen {" &
                           """width"": " & integer'image(WIDTH) & ", " &
                           """depth"": " & integer'image(DEPTH) & 
                           "}" severity note;
  end generate;

  process(clk)
  begin
    if rising_edge(clk) then
      r_valid <= ar_valid;
      if reset = '1' then
        r_valid <= '0';
      end if;
    end if;
  end process;

end architecture;
