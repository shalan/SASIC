module rv32e_cpu #(
    parameter RESET_ADDR = 32'h0000_0000
)(
    input wire clk,
    input wire reset_n,
    
    // Instruction Memory Interface
    output wire [31:0] imem_addr,
    input wire [31:0] imem_data,
    
    // Data Memory Interface  
    output wire [31:0] dmem_addr,
    output wire [31:0] dmem_wdata,
    input wire [31:0] dmem_rdata,
    output wire [3:0] dmem_we,
    output wire dmem_en
);

    // Pipeline Registers
    reg [31:0] pc;
    reg [31:0] pc_plus4;
    reg [31:0] instruction;
    reg [31:0] ex_pc, ex_pc_plus4;
    reg [31:0] ex_instruction;
    reg [31:0] ex_rs1_data, ex_rs2_data;
    reg [31:0] ex_immediate;
    reg [4:0] ex_rd_addr;
    reg ex_reg_write, ex_mem_read, ex_mem_write;
    reg [2:0] ex_alu_op;
    reg ex_branch, ex_jump;
    
    // Register File (16 registers for RV32E)
    reg [31:0] regfile [0:15];
    
    // Control and Data Signals
    wire [4:0] rs1_addr, rs2_addr, rd_addr;
    wire [31:0] rs1_data, rs2_data;
    wire [31:0] immediate;
    wire reg_write, mem_read, mem_write, branch, jump;
    wire [2:0] alu_op;
    wire [6:0] opcode;
    wire [2:0] funct3;
    wire [6:0] funct7;
    
    // ALU
    wire [31:0] alu_result;
    wire alu_zero;
    
    // Pipeline Control
    reg pipeline_stall;
    reg pipeline_flush;
    wire branch_taken;
    wire [31:0] branch_target;
    
    // Forwarding
    wire forward_rs1, forward_rs2;
    wire [31:0] forward_rs1_data, forward_rs2_data;

    //=================================================================
    // Stage 1: Instruction Fetch & Decode (IF/ID)
    //=================================================================
    
    // Program Counter
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            pc <= RESET_ADDR;
        end else if (!pipeline_stall) begin
            if (pipeline_flush) begin
                pc <= branch_target;
            end else begin
                pc <= pc + 4;
            end
        end
    end
    
    assign imem_addr = pc;
    
    // Instruction Decode
    assign opcode = imem_data[6:0];
    assign rd_addr = imem_data[11:7];
    assign funct3 = imem_data[14:12];
    assign rs1_addr = imem_data[19:15];
    assign rs2_addr = imem_data[24:20];
    assign funct7 = imem_data[31:25];
    
    // Register File Read (RV32E: only 16 registers)
    assign rs1_data = (rs1_addr == 5'b0) ? 32'b0 : regfile[rs1_addr[3:0]];
    assign rs2_data = (rs2_addr == 5'b0) ? 32'b0 : regfile[rs2_addr[3:0]];
    
    // Immediate Generation
    reg [31:0] imm_gen;
    always @(*) begin
        case (opcode)
            7'b0010011, 7'b0000011: // I-type (ADDI, LW, etc.)
                imm_gen = {{20{imem_data[31]}}, imem_data[31:20]};
            7'b0100011: // S-type (SW, etc.)
                imm_gen = {{20{imem_data[31]}}, imem_data[31:25], imem_data[11:7]};
            7'b1100011: // B-type (BEQ, etc.)
                imm_gen = {{19{imem_data[31]}}, imem_data[31], imem_data[7], 
                           imem_data[30:25], imem_data[11:8], 1'b0};
            7'b0110111: // U-type (LUI)
                imm_gen = {imem_data[31:12], 12'b0};
            7'b1101111: // J-type (JAL)
                imm_gen = {{11{imem_data[31]}}, imem_data[31], imem_data[19:12],
                           imem_data[20], imem_data[30:21], 1'b0};
            default:
                imm_gen = 32'b0;
        endcase
    end
    
    assign immediate = imm_gen;
    
    // Control Unit - Simplified for common RV32E instructions
    reg ctrl_reg_write, ctrl_mem_read, ctrl_mem_write, ctrl_branch, ctrl_jump;
    reg [2:0] ctrl_alu_op;
    
    always @(*) begin
        // Defaults
        ctrl_reg_write = 1'b0;
        ctrl_mem_read = 1'b0;
        ctrl_mem_write = 1'b0;
        ctrl_branch = 1'b0;
        ctrl_jump = 1'b0;
        ctrl_alu_op = 3'b000;
        
        case (opcode)
            7'b0110011: begin // R-type (ADD, SUB, etc.)
                ctrl_reg_write = 1'b1;
                ctrl_alu_op = {funct7[5], funct3[2:0]}; // Includes SUB bit
            end
            7'b0010011: begin // I-type (ADDI, etc.)
                ctrl_reg_write = 1'b1;
                ctrl_alu_op = {1'b0, funct3};
            end
            7'b0000011: begin // Load (LW, LH, LB)
                ctrl_reg_write = 1'b1;
                ctrl_mem_read = 1'b1;
                ctrl_alu_op = 3'b000; // ADD for address calculation
            end
            7'b0100011: begin // Store (SW, SH, SB)
                ctrl_mem_write = 1'b1;
                ctrl_alu_op = 3'b000; // ADD for address calculation
            end
            7'b1100011: begin // Branch (BEQ, BNE, etc.)
                ctrl_branch = 1'b1;
                ctrl_alu_op = 3'b001; // SUB for comparison
            end
            7'b1101111: begin // JAL
                ctrl_reg_write = 1'b1;
                ctrl_jump = 1'b1;
            end
            7'b0110111: begin // LUI
                ctrl_reg_write = 1'b1;
                ctrl_alu_op = 3'b110; // Pass immediate
            end
        endcase
    end
    
    assign reg_write = ctrl_reg_write;
    assign mem_read = ctrl_mem_read;
    assign mem_write = ctrl_mem_write;
    assign branch = ctrl_branch;
    assign jump = ctrl_jump;
    assign alu_op = ctrl_alu_op;

    //=================================================================
    // Pipeline Register: IF/ID -> EX
    //=================================================================
    
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            ex_pc <= 32'b0;
            ex_pc_plus4 <= 32'b0;
            ex_instruction <= 32'b0;
            ex_rs1_data <= 32'b0;
            ex_rs2_data <= 32'b0;
            ex_immediate <= 32'b0;
            ex_rd_addr <= 5'b0;
            ex_reg_write <= 1'b0;
            ex_mem_read <= 1'b0;
            ex_mem_write <= 1'b0;
            ex_alu_op <= 3'b0;
            ex_branch <= 1'b0;
            ex_jump <= 1'b0;
        end else if (!pipeline_stall) begin
            if (pipeline_flush) begin
                // Insert NOP
                ex_instruction <= 32'h00000013; // ADDI x0, x0, 0 (NOP)
                ex_reg_write <= 1'b0;
                ex_mem_read <= 1'b0;
                ex_mem_write <= 1'b0;
                ex_branch <= 1'b0;
                ex_jump <= 1'b0;
            end else begin
                ex_pc <= pc;
                ex_pc_plus4 <= pc + 4;
                ex_instruction <= imem_data;
                ex_rs1_data <= rs1_data;
                ex_rs2_data <= rs2_data;
                ex_immediate <= immediate;
                ex_rd_addr <= rd_addr;
                ex_reg_write <= reg_write;
                ex_mem_read <= mem_read;
                ex_mem_write <= mem_write;
                ex_alu_op <= alu_op;
                ex_branch <= branch;
                ex_jump <= jump;
            end
        end
    end

    //=================================================================
    // Stage 2: Execute (EX)
    //=================================================================
    
    // Simple Forwarding Logic
    assign forward_rs1 = (ex_rd_addr != 5'b0) && (ex_rd_addr == rs1_addr) && ex_reg_write;
    assign forward_rs2 = (ex_rd_addr != 5'b0) && (ex_rd_addr == rs2_addr) && ex_reg_write;
    assign forward_rs1_data = forward_rs1 ? alu_result : ex_rs1_data;
    assign forward_rs2_data = forward_rs2 ? alu_result : ex_rs2_data;
    
    // ALU
    reg [31:0] alu_a, alu_b;
    always @(*) begin
        alu_a = forward_rs1_data;
        case (ex_instruction[6:0])
            7'b0010011, 7'b0000011, 7'b0100011: // I-type, Load, Store
                alu_b = ex_immediate;
            7'b0110111: // LUI
                alu_b = ex_immediate;
            default: // R-type
                alu_b = forward_rs2_data;
        endcase
    end
    
    reg [31:0] alu_out;
    always @(*) begin
        case (ex_alu_op)
            3'b000: alu_out = alu_a + alu_b;              // ADD
            3'b001: alu_out = alu_a - alu_b;              // SUB  
            3'b010: alu_out = ($signed(alu_a) < $signed(alu_b)) ? 1 : 0; // SLT
            3'b011: alu_out = (alu_a < alu_b) ? 1 : 0;    // SLTU
            3'b100: alu_out = alu_a ^ alu_b;              // XOR
            3'b101: alu_out = alu_a >> alu_b[4:0];        // SRL (simplified)
            3'b110: alu_out = alu_b;                      // Pass B (for LUI)
            3'b111: alu_out = alu_a & alu_b;              // AND
            default: alu_out = 32'b0;
        endcase
    end
    
    assign alu_result = alu_out;
    assign alu_zero = (alu_result == 32'b0);
    
    // Branch Logic (simplified)
    reg branch_condition;
    always @(*) begin
        case (ex_instruction[14:12]) // funct3
            3'b000: branch_condition = alu_zero;           // BEQ
            3'b001: branch_condition = !alu_zero;          // BNE
            3'b100: branch_condition = alu_result[0];      // BLT (simplified)
            3'b101: branch_condition = !alu_result[0];     // BGE (simplified)
            default: branch_condition = 1'b0;
        endcase
    end
    
    assign branch_taken = (ex_branch && branch_condition) || ex_jump;
    assign branch_target = ex_jump ? (ex_pc + ex_immediate) : 
                          (ex_branch && branch_condition) ? (ex_pc + ex_immediate) : 
                          (ex_pc + 4);

    //=================================================================
    // Stage 3: Write Back (WB)
    //=================================================================
    
    // Memory Interface
    assign dmem_addr = alu_result;
    assign dmem_wdata = forward_rs2_data;
    assign dmem_we = ex_mem_write ? 4'hF : 4'h0; // Simplified: word writes only
    assign dmem_en = ex_mem_read || ex_mem_write;
    
    // Register File Write (RV32E: only lower 4 bits matter)
    wire [31:0] wb_data;
    assign wb_data = ex_mem_read ? dmem_rdata : 
                     ex_jump ? ex_pc_plus4 : 
                     alu_result;
    
    always @(posedge clk) begin
        if (ex_reg_write && ex_rd_addr != 5'b0) begin
            regfile[ex_rd_addr[3:0]] <= wb_data;
        end
    end

    //=================================================================
    // Pipeline Control
    //=================================================================
    
    // Simple stall logic for load-use hazard
    wire load_use_hazard;
    assign load_use_hazard = ex_mem_read && 
                            ((ex_rd_addr == rs1_addr) || (ex_rd_addr == rs2_addr)) &&
                            (ex_rd_addr != 5'b0);
    
    always @(*) begin
        pipeline_stall = load_use_hazard;
        pipeline_flush = branch_taken;
    end

    // Initialize register file
    integer i;
    initial begin
        for (i = 0; i < 16; i = i + 1) begin
            regfile[i] = 32'b0;
        end
    end

endmodule
