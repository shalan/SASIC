module spi_master #(
    parameter DATA_WIDTH = 8,           // Configurable data width
    parameter CLOCK_DIV = 4,            // SPI clock divider (system_clk / CLOCK_DIV)
    parameter CPOL = 1'b0,              // Clock polarity
    parameter CPHA = 1'b0               // Clock phase
)(
    // System interface
    input wire clk,                     // System clock
    input wire reset_n,                 // Active low reset
    
    // Control interface
    input wire start,                   // Start transaction
    input wire [DATA_WIDTH-1:0] tx_data, // Data to transmit
    output reg [DATA_WIDTH-1:0] rx_data, // Received data
    output reg busy,                    // Transaction in progress
    output reg done,                    // Transaction complete (1 clock pulse)
    
    // SPI interface
    output reg sclk,                    // SPI clock
    output reg mosi,                    // Master out, slave in
    input wire miso,                    // Master in, slave out
    output reg cs_n                     // Chip select (active low)
);

    // Internal registers and wires
    reg [$clog2(CLOCK_DIV)-1:0] clk_counter;
    reg [$clog2(DATA_WIDTH)-1:0] bit_counter;
    reg [DATA_WIDTH-1:0] tx_shift_reg;
    reg [DATA_WIDTH-1:0] rx_shift_reg;
    reg sclk_enable;
    wire sclk_edge;
    
    // State machine states
    localparam IDLE       = 2'b00;
    localparam LOAD       = 2'b01;
    localparam TRANSFER   = 2'b10;
    localparam COMPLETE   = 2'b11;
    
    reg [1:0] state, next_state;

    // Clock divider for SPI clock generation
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            clk_counter <= 0;
        end else if (sclk_enable) begin
            if (clk_counter == CLOCK_DIV-1) begin
                clk_counter <= 0;
            end else begin
                clk_counter <= clk_counter + 1;
            end
        end else begin
            clk_counter <= 0;
        end
    end

    // Generate SPI clock edge detection
    assign sclk_edge = sclk_enable && (clk_counter == CLOCK_DIV-1);

    // SPI clock generation based on CPOL
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            sclk <= CPOL;
        end else if (sclk_edge) begin
            sclk <= ~sclk;
        end else if (!sclk_enable) begin
            sclk <= CPOL;
        end
    end

    // State machine - sequential logic
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state <= IDLE;
        end else begin
            state <= next_state;
        end
    end

    // State machine - combinational logic
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (start) begin
                    next_state = LOAD;
                end
            end
            
            LOAD: begin
                next_state = TRANSFER;
            end
            
            TRANSFER: begin
                if (bit_counter == 0 && sclk_edge && 
                    ((CPHA == 1'b0 && sclk == ~CPOL) || 
                     (CPHA == 1'b1 && sclk == CPOL))) begin
                    next_state = COMPLETE;
                end
            end
            
            COMPLETE: begin
                next_state = IDLE;
            end
        endcase
    end

    // Output logic and data shifting
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            busy <= 1'b0;
            done <= 1'b0;
            cs_n <= 1'b1;
            mosi <= 1'b0;
            rx_data <= 0;
            tx_shift_reg <= 0;
            rx_shift_reg <= 0;
            bit_counter <= 0;
            sclk_enable <= 1'b0;
        end else begin
            done <= 1'b0; // Default: done is a pulse
            
            case (state)
                IDLE: begin
                    busy <= 1'b0;
                    cs_n <= 1'b1;
                    sclk_enable <= 1'b0;
                    mosi <= 1'b0;
                end
                
                LOAD: begin
                    busy <= 1'b1;
                    cs_n <= 1'b0;
                    tx_shift_reg <= tx_data;
                    bit_counter <= DATA_WIDTH - 1;
                    sclk_enable <= 1'b1;
                    
                    // For CPHA=0, data is valid on first clock edge
                    if (CPHA == 1'b0) begin
                        mosi <= tx_data[DATA_WIDTH-1];
                    end
                end
                
                TRANSFER: begin
                    if (sclk_edge) begin
                        if ((CPHA == 1'b0 && sclk == CPOL) || 
                            (CPHA == 1'b1 && sclk == ~CPOL)) begin
                            // Sample MISO (read edge)
                            rx_shift_reg <= {rx_shift_reg[DATA_WIDTH-2:0], miso};
                        end
                        
                        if ((CPHA == 1'b0 && sclk == ~CPOL) || 
                            (CPHA == 1'b1 && sclk == CPOL)) begin
                            // Update MOSI (write edge)
                            if (bit_counter > 0) begin
                                bit_counter <= bit_counter - 1;
                                tx_shift_reg <= {tx_shift_reg[DATA_WIDTH-2:0], 1'b0};
                                mosi <= tx_shift_reg[DATA_WIDTH-2];
                            end else begin
                                sclk_enable <= 1'b0;
                            end
                        end
                    end
                end
                
                COMPLETE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    cs_n <= 1'b1;
                    rx_data <= rx_shift_reg;
                end
            endcase
        end
    end

endmodule
