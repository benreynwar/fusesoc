library ieee;

use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.logceil.all;

entity shift_register is
  generic (
    WIDTH: positive := 4;
    DEPTH: positive := 6;
    TARGET: string := "XILINX";
    DEPTH_CUTOFF: positive := 32
    );
  port (
    clk: in std_logic;
    reset: in std_logic;
    i_valid: in std_logic;
    i_data: in std_logic_vector(WIDTH-1 downto 0);
    o_valid: out std_logic;
    o_data: out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;

architecture arch of shift_register is
  signal write_address: unsigned(logceil(DEPTH)-1 downto 0);
  signal read_address: unsigned(logceil(DEPTH)-1 downto 0);
  signal write_address_slv: std_logic_vector(logceil(DEPTH)-1 downto 0);
  signal read_address_slv: std_logic_vector(logceil(DEPTH)-1 downto 0);
  subtype t_data is std_logic_vector(WIDTH-1 downto 0);
  type array_of_data is array(natural range <>) of t_data;
  signal datas: array_of_data(DEPTH-1 downto 0);
  signal valids: std_logic_vector(DEPTH-1 downto 0);
begin

  shallow: if DEPTH <= DEPTH_CUTOFF generate
    datas(DEPTH-1) <= i_data;
    valids(DEPTH-1) <= i_valid;
    process(clk)
    begin
      if rising_edge(clk) then
        if i_valid = '1' then
          for ii in 0 to DEPTH-2 loop
            datas(ii) <= datas(ii+1);
            valids(ii) <= valids(ii+1);
          end loop;
        end if;
      end if;
    end process;
    o_data <= datas(0);
    o_valid <= valids(0);
  end generate;

  deep: if DEPTH > DEPTH_CUTOFF generate

    read_address_slv <= std_logic_vector(read_address);
    write_address_slv <= std_logic_vector(write_address);

    process(clk)
    begin
      if rising_edge(clk) then
        if i_valid = '1' then
          if write_address = DEPTH-1 then
            write_address <= (others => '0');
          else
            write_address <= write_address + 1;
          end if;
          if read_address = DEPTH-1 then
            read_address <= (others => '0');
          else
            read_address <= read_address + 1;
          end if;
          if reset = '1' then
            write_address <= to_unsigned(0, logceil(DEPTH));
            read_address <= to_unsigned(DEPTH-1, logceil(DEPTH));
          end if;
        end if;
      end if;
    end process;

    mema: entity work.xilinx_bram_wrapper
      generic map (
        WIDTH => WIDTH,
        DEPTH => DEPTH
        )
      port map (
        clk => clk,
        reset => reset,
        w_valid => '1',
        w_address => write_address_slv,
        w_data => i_data,
        ar_valid => '1',
        ar_address => read_address_slv,
        r_data => o_data
        );

  end generate;

end architecture;
