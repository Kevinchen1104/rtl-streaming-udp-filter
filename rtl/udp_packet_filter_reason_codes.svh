// Values reported on result_reason. See docs/spec.md, "Result reasons".
//
// Included inside each module that needs them, so there is no include
// guard. A package would be the usual choice, but the open-source Yosys
// frontend does not support `import`.
localparam logic [3:0] REASON_ACCEPT                  = 4'd0;
localparam logic [3:0] REASON_NON_IPV4                = 4'd1;
localparam logic [3:0] REASON_BAD_IPV4_HEADER         = 4'd2;
localparam logic [3:0] REASON_NON_UDP                 = 4'd3;
localparam logic [3:0] REASON_FRAGMENTED              = 4'd4;
localparam logic [3:0] REASON_BAD_LENGTH_OR_TRUNCATED = 4'd5;
localparam logic [3:0] REASON_DST_PORT_MISMATCH       = 4'd6;
localparam logic [3:0] REASON_MSG_TYPE_MISMATCH       = 4'd7;
localparam logic [3:0] REASON_FRAME_TOO_LONG          = 4'd8;
