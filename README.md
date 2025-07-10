# SASIC - Sky130 Structured ASIC Toolchain
## 1. PROJECT OVERVIEW

### 1.1 Mission Statement
Develop a complete open-source tool (gen_fabric.py) that generates Sky130-based structured ASIC fabrics from JSON specifications, enabling rapid prototyping and low-volume production with 70-80% cost reduction and 2-4 week turnaround times.

### 1.2 Value Proposition
- **Cost Reduction:** 70-80% lower fabrication costs vs. full-custom ASIC
- **Time-to-Market:** 2-4 weeks vs. 12-20 weeks for traditional ASIC
- **Risk Mitigation:** Pre-characterized fabric eliminates yield uncertainty
- **Accessibility:** Open-source tools democratize ASIC design

### 1.3 Technical Approach
Pre-fabricate base wafers containing regular arrays of Sky130 standard cells with fixed power network (met1-met2). Custom designs require fabrication of only top 3 metal layers (met3-met5) and vias.

---

## 2. Fabric Generator (gen_fabric.py) - Complete Formal Requirements Specification

## FUNCTIONAL REQUIREMENTS

### 2.1 Core Functionality
- **REQ-FUNC-001:** The tool SHALL generate structured ASIC fabrics from JSON input specifications
- **REQ-FUNC-002:** The tool SHALL support tile-based fabric composition with default tiles and regional overrides
- **REQ-FUNC-003:** The tool SHALL generate unique cell instance names following the specified naming convention
- **REQ-FUNC-004:** The tool SHALL detect and report overlaps, gaps, and inconsistencies in fabric definitions
- **REQ-FUNC-005:** The tool SHALL generate multiple output formats: DEF, LEF, JSON, and SVG
- **REQ-FUNC-006:** The tool SHALL support edge cell placement around fabric perimeter
- **REQ-FUNC-007:** The tool SHALL support core area placement with configurable margins
- **REQ-FUNC-008:** The tool SHALL support both automatic and manual I/O pin positioning

### 2.2 Input Processing
- **REQ-INPUT-001:** The tool SHALL accept three JSON input files: technology definition, tile definitions, and fabric configuration
- **REQ-INPUT-002:** The tool SHALL validate all input files for completeness and consistency before processing
- **REQ-INPUT-003:** The tool SHALL support technology-specific cell libraries as defined in the technology JSON

### 2.3 Fabric Generation
- **REQ-FAB-001:** The tool SHALL initialize fabric arrays with default tile types
- **REQ-FAB-002:** The tool SHALL apply regional tile type overrides to specified rectangular areas
- **REQ-FAB-003:** The tool SHALL support arbitrary fabric dimensions specified in the configuration
- **REQ-FAB-004:** The tool SHALL generate I/O rings with configurable pin placement on fabric edges
- **REQ-FAB-005:** The tool SHALL calculate fabric dimensions including edge cells for core area sizing

---

## 3. INPUT SPECIFICATIONS

### 3.1 Technology File (sky130_hd.json)
```json
{
  "technology": "sky130",
  "version": "1.0.1", 
  "description": "Sky130 HD standard cell library for structured ASIC",
  "units": {
    "distance": 1000,
    "time": 1000,
    "capacitance": 1000,
    "resistance": 1000,
    "current": 1000
  },
  "site": {
    "name": "unithd",
    "width": 0.46,
    "height": 2.72
  },
  "cells": [
    {
      "name": "sky130_fd_sc_hd__nand2_2",
      "alias": "NAND2",
      "width": 5,
      "height": 1,
      "drive_strength": 2,
      "cell_type": "logic",
      "pins": {
        "A": {
          "direction": "input",
          "capacitance": 0.004431,
          "layer": "li1"
        },
        "B": {
          "direction": "input", 
          "capacitance": 0.004418,
          "layer": "li1"
        },
        "Y": {
          "direction": "output",
          "function": "Y=!(A&B)",
          "max_capacitance": 0.295725,
          "max_fanout": 8,
          "layer": "li1"
        }
      },
      "timing": {
        "A_to_Y": {"rise": 0.1156314, "fall": 0.0890522},
        "B_to_Y": {"rise": 0.125234, "fall": 0.0925028}
      },
      "power": {
        "leakage": 0.002459623
      }
    }
  ],
  "layers": {
    "met3": {
      "direction": "horizontal",
      "pitch": 0.48,
      "min_width": 0.30,
      "programmable": true
    },
    "met4": {
      "direction": "vertical", 
      "pitch": 0.96,
      "min_width": 0.30,
      "programmable": true
    },
    "met5": {
      "direction": "horizontal",
      "pitch": 1.44,
      "min_width": 0.30,
      "programmable": true
    }
  }
}
```

**Requirements:**
- **REQ-TECH-001:** Technology file SHALL define standard cell library with aliases, widths, and pin information
- **REQ-TECH-002:** Function field SHALL be located in output pin objects, not at cell level
- **REQ-TECH-003:** Technology file SHALL specify routing layers met3-met5 as programmable
- **REQ-TECH-004:** Site definition SHALL specify physical dimensions for placement calculations

### 3.2 Tile Definitions (tiles.json)
```json
{
  "tiles": [
    {
      "name": "Logic_4x60",
      "description": "4-row logic tile with 60 sites per row",
      "height": 4,
      "width": 60,
      "site": "unithd", 
      "rows": [
        {
          "row_id": 0,
          "cells": [
            {"type": "TAP", "count": 1},
            {"type": "NAND2", "count": 5},
            {"type": "DECAP4", "count": 1},
            {"type": "TAP", "count": 1}
          ]
        },
        {
          "row_id": 1,
          "cells": [
            {"type": "TAP", "count": 1},
            {"type": "NAND2", "count": 3},
            {"type": "INV", "count": 2}
          ]
        }
      ]
    }
  ]
}
```

**Requirements:**
- **REQ-TILE-001:** Tile definitions SHALL specify height, width, and cell composition for each row
- **REQ-TILE-002:** Cell types SHALL reference aliases defined in technology file
- **REQ-TILE-003:** Tiles SHALL support mixed cell types within rows
- **REQ-TILE-004:** Tile width SHALL be specified in site units

### 3.3 Fabric Configuration (fabric.json)
```json
{
  "name": "Fabric_5x5",
  "description": "5x5 structured ASIC fabric with edge cells",
  "array_dimensions": {"rows": 5, "cols": 5},
  "tile_configuration": {
    "default_tile": "Logic_4x60",
    "regions": [
      {
        "name": "memory_block",
        "tile_type": "Memory_4x60", 
        "area": {"row_start": 2, "col_start": 2, "width": 2, "height": 2}
      }
    ]
  },
  "edge_cells": {
    "left": {"enable": true, "cell": "DECAP12"},
    "right": {"enable": true, "cell": "DECAP12"}, 
    "top": {"enable": true, "cell": "DECAP4"},
    "bottom": {"enable": true, "cell": "DECAP4"}
  },
  "io_ring": {
    "pin_size": {"width": 1.0, "height": 1.0},
    "edges": {
      "north": {
        "spacing": "manual",
        "pins": [
          {"name": "clk_in", "type": "clock", "direction": "input", "position": 25.5},
          {"name": "data_in_0", "type": "data", "direction": "input", "position": 75.0}
        ]
      },
      "south": {
        "spacing": "auto",
        "pins": [
          {"name": "data_out_0", "type": "data", "direction": "output"},
          {"name": "data_out_1", "type": "data", "direction": "output"}
        ]
      }
    }
  },
  "margins": {
    "horizontal": 50.0,
    "vertical": 30.0
  },
  "power_distribution": {
    "primary_grid": {
      "VDD": {"layer": "met4", "pitch": 27.6, "width": 2.0},
      "VSS": {"layer": "met4", "pitch": 27.6, "width": 2.0}
    },
    "secondary_grid": {
      "VDD": {"layer": "met3", "pitch": 13.8, "width": 1.0},
      "VSS": {"layer": "met3", "pitch": 13.8, "width": 1.0}
    }
  }
}
```

**Requirements:**
- **REQ-FAB-006:** Fabric configuration SHALL specify array dimensions and default tile type
- **REQ-FAB-007:** Regions SHALL support rectangular areas with row_start, col_start, width, height
- **REQ-FAB-008:** I/O ring SHALL support pin placement on north, south, east, west edges
- **REQ-FAB-009:** Power distribution SHALL specify primary and secondary grid parameters
- **REQ-FAB-010:** Edge cells SHALL be optionally specified for each fabric edge
- **REQ-FAB-011:** Margins SHALL be specified when I/O pins are defined
- **REQ-FAB-012:** I/O ring SHALL support configurable pin sizing and positioning

---

## 4. EDGE CELL REQUIREMENTS

### 4.1 Edge Cell Configuration
- **REQ-EDGE-001:** The tool SHALL support edge cell placement around fabric perimeter
- **REQ-EDGE-002:** Edge cells SHALL be specified in fabric JSON under "edge_cells" section
- **REQ-EDGE-003:** Edge cell specification SHALL include enable flag and cell type for each edge
- **REQ-EDGE-004:** Edge cell types SHALL exist in technology definition

### 4.2 Edge Cell Placement Rules
- **REQ-EDGE-005:** Left/right edge cells SHALL be placed one per fabric row
- **REQ-EDGE-006:** Left edge cells SHALL be positioned at x=0 of core area
- **REQ-EDGE-007:** Right edge cells SHALL be positioned at x=left_width+fabric_width
- **REQ-EDGE-008:** Top/bottom edge cells SHALL span the full core width including edge cell areas
- **REQ-EDGE-009:** Edge cells SHALL be placed adjacent with no spacing
- **REQ-EDGE-010:** Edge cells SHALL expand core area dimensions

### 4.3 Edge Cell Coordinate System
- **REQ-EDGE-011:** For 5×5 fabric with 4×60 tiles and DECAP12 left/right edges:
  - Fabric dimensions: 20 rows × 300 sites
  - Left edge: 20 DECAP12 cells at columns 0-11
  - Right edge: 20 DECAP12 cells at columns 312-323
  - Core area: 324 sites × 20 rows total

- **REQ-EDGE-012:** Edge cells SHALL be included in core area dimension calculations
- **REQ-EDGE-013:** Edge cells SHALL be included in DEF file as components
- **REQ-EDGE-014:** Edge cells SHALL be included in statistics and cell counts
- **REQ-EDGE-015:** Edge cells SHALL use naming convention: CELLTYPE_EDGE_DIRECTION_INDEX
- **REQ-EDGE-016:** Example: DECAP12_EDGE_LEFT_0, DECAP4_EDGE_TOP_15

---

## 5. MARGIN AND CORE AREA REQUIREMENTS

### 5.1 Margin Specification
- **REQ-MARGIN-001:** Fabric JSON SHALL support margin specification when I/O pins are defined
- **REQ-MARGIN-002:** Margins SHALL define core area placement within die area
- **REQ-MARGIN-003:** Margin values SHALL be specified in microns
- **REQ-MARGIN-004:** Margins SHALL be positive numbers

### 5.2 Core Area Definition
- **REQ-MARGIN-005:** Core area SHALL contain fabric including edge cells
- **REQ-MARGIN-006:** Margin area SHALL be available for I/O pins and power rings
- **REQ-MARGIN-007:** Die area = Core area + 2×margins
- **REQ-MARGIN-008:** Core area placement = (margin_horizontal, margin_vertical) offset from die origin
- **REQ-MARGIN-009:** All cell coordinates SHALL be offset by margin values

---

## 6. I/O RING PIN POSITIONING REQUIREMENTS

### 6.1 Pin Location Specification
- **REQ-PIN-001:** I/O ring SHALL support both automatic and manual pin positioning
- **REQ-PIN-002:** Pin positioning mode SHALL be specified per edge using "spacing" attribute
- **REQ-PIN-003:** Automatic spacing SHALL use "spacing": "auto"
- **REQ-PIN-004:** Manual positioning SHALL use "spacing": "manual"
- **REQ-PIN-005:** Manual positioning SHALL require position field for each pin

### 6.2 Pin Size Configuration
- **REQ-PIN-006:** Pin physical size SHALL be configurable via "pin_size" attribute in fabric JSON
- **REQ-PIN-007:** Pin size SHALL default to 1×1 database units if not specified
- **REQ-PIN-008:** Pin size SHALL be configurable via command line argument --pin-size
- **REQ-PIN-009:** Command line pin size SHALL override JSON specification
- **REQ-PIN-010:** Pin size SHALL be specified in database units or microns

### 6.3 Position Coordinate System
- **REQ-PIN-011:** Pin positions SHALL be specified in microns from die corner
- **REQ-PIN-012:** Position coordinate directions SHALL be:
  - North edge: 0.0 = left corner, increases rightward
  - South edge: 0.0 = left corner, increases rightward
  - East edge: 0.0 = bottom corner, increases upward
  - West edge: 0.0 = bottom corner, increases upward

### 6.4 Pin Positioning Validation
- **REQ-PIN-013:** Manual pin positions SHALL not overlap with each other
- **REQ-PIN-014:** Pins SHALL be positioned within margin areas only
- **REQ-PIN-015:** Pins SHALL not extend into core area
- **REQ-PIN-016:** Pin positions SHALL be validated against die boundary limits

### 6.5 Mixed Mode Validation
- **REQ-PIN-017:** Manual and auto spacing SHALL NOT be mixed on same edge
- **REQ-PIN-018:** All pins on manual spacing edge SHALL specify position field
- **REQ-PIN-019:** Missing position field in manual mode SHALL trigger error
- **REQ-PIN-020:** Position field in auto mode SHALL trigger warning and be ignored

### 6.6 Backward Compatibility
- **REQ-PIN-021:** Existing "spacing": "auto" format SHALL continue to work unchanged
- **REQ-PIN-022:** Edges without spacing specification SHALL default to auto mode
- **REQ-PIN-023:** Auto spacing SHALL distribute pins evenly as before

---

## 7. PROCESSING REQUIREMENTS

### 7.1 Coordinate System
- **REQ-COORD-001:** All coordinates SHALL use 0-based indexing
- **REQ-COORD-002:** Fabric array coordinates SHALL be (row, col) where row ∈ [0, rows-1], col ∈ [0, cols-1]
- **REQ-COORD-003:** Tile cell coordinates SHALL be (row_id, cell_position) within tile boundaries
- **REQ-COORD-004:** Physical coordinates SHALL be calculated from site dimensions (0.46μm × 2.72μm)
- **REQ-COORD-005:** Physical coordinates SHALL account for edge cell offsets
- **REQ-COORD-006:** Physical coordinates SHALL account for margin offsets when specified

### 7.2 Fabric Dimension Calculations
- **REQ-COORD-007:** Fabric dimensions SHALL be calculated as: tiles × tile_dimensions
- **REQ-COORD-008:** For N×M tile array with H×W tiles: fabric = (N×H) rows × (M×W) sites
- **REQ-COORD-009:** Core area SHALL include fabric + edge cell dimensions
- **REQ-COORD-010:** Die area SHALL include core area + 2×margins

### 7.3 Region Processing Algorithm
- **REQ-PROC-001:** Fabric array SHALL be initialized with default_tile type
- **REQ-PROC-002:** Regions SHALL be processed in definition order
- **REQ-PROC-003:** Region coverage SHALL be calculated as:
  - Row range: [row_start, row_start + height - 1]
  - Column range: [col_start, col_start + width - 1]
- **REQ-PROC-004:** Overlapping regions SHALL trigger validation errors

### 7.4 Cell Naming Convention
- **REQ-NAME-001:** Cell instance names SHALL follow format: CELLTYPE_TX-Y_CX-Y
- **REQ-NAME-002:** CELLTYPE SHALL be the cell alias from technology file
- **REQ-NAME-003:** TX-Y SHALL represent tile position (T + row + "-" + col)
- **REQ-NAME-004:** CX-Y SHALL represent cell position within tile (C + row_id + "-" + cell_position)
- **REQ-NAME-005:** Example: NAND2_T2-3_C1-4 for NAND2 in tile (2,3) at cell position (1,4)

### 7.5 Edge Cell Processing
- **REQ-PROC-005:** Edge cells SHALL be generated based on fabric row/site dimensions
- **REQ-PROC-006:** Left/right edge cells SHALL be generated one per fabric row
- **REQ-PROC-007:** Top/bottom edge cells SHALL span complete core width
- **REQ-PROC-008:** Edge cell coordinates SHALL account for other edge cells

---

## 8. VALIDATION REQUIREMENTS

### 8.1 Input Validation
- **REQ-VAL-001:** Unknown cell types SHALL trigger validation errors
- **REQ-VAL-002:** Unknown tile types SHALL trigger validation errors
- **REQ-VAL-003:** Missing technology definitions SHALL trigger validation errors
- **REQ-VAL-004:** Malformed JSON SHALL trigger parsing errors with line numbers

### 8.2 Tile Validation
- **REQ-VAL-005:** Sum of cell widths per row SHALL equal declared tile width
- **REQ-VAL-006:** All rows within a tile SHALL have identical total width
- **REQ-VAL-007:** Adjacent cells within rows SHALL NOT overlap sites
- **REQ-VAL-008:** Gaps between cells within rows SHALL be reported as errors
- **REQ-VAL-009:** Cell count and type consistency SHALL be validated

### 8.3 Fabric Validation
- **REQ-VAL-010:** Regions SHALL NOT extend beyond fabric array boundaries
- **REQ-VAL-011:** Overlapping regions SHALL trigger validation errors
- **REQ-VAL-012:** Region boundaries SHALL be validated: row_start + height ≤ array_rows
- **REQ-VAL-013:** Region boundaries SHALL be validated: col_start + width ≤ array_cols

### 8.4 Edge Cell Validation
- **REQ-VAL-014:** Edge cell types SHALL exist in technology definition
- **REQ-VAL-015:** Edge cell specifications SHALL be validated for completeness
- **REQ-VAL-016:** Disabled edges SHALL be ignored in processing

### 8.5 Margin Validation
- **REQ-VAL-017:** Margins SHALL be specified when I/O pins are defined
- **REQ-VAL-018:** Margin values SHALL be positive numbers
- **REQ-VAL-019:** Core area SHALL fit within die area including margins

### 8.6 Pin Position Validation
- **REQ-VAL-020:** For each manually positioned pin, validate:
  - Position ≥ margin_start for that edge
  - Position + pin_size ≤ edge_length - margin_end
  - Pin rectangle does not overlap with other pins
  - Pin rectangle fits within margin boundaries

- **REQ-VAL-021:** Pin overlap detection SHALL check rectangular boundaries
- **REQ-VAL-022:** Margin boundary validation SHALL ensure pins remain in margin areas

### 8.7 Error Handling
- **REQ-ERR-001:** Validation errors SHALL halt processing and report specific issues
- **REQ-ERR-002:** Error messages SHALL include position information (tile, row, cell coordinates)
- **REQ-ERR-003:** Multiple errors SHALL be collected and reported together when possible
- **REQ-ERR-004:** Error severity levels SHALL be: ERROR (fatal), WARNING (non-fatal)

---

## 9. OUTPUT REQUIREMENTS

### 9.1 DEF File Output
- **REQ-OUT-001:** DEF file SHALL contain complete fabric layout with placed cells
- **REQ-OUT-002:** DEF file SHALL include physical coordinates for each cell instance
- **REQ-OUT-003:** DEF file SHALL use generated cell instance names
- **REQ-OUT-004:** DEF file SHALL include power rail definitions
- **REQ-OUT-005:** DEF file SHALL be compatible with OpenROAD tools
- **REQ-OUT-006:** DEF DIEAREA SHALL include margins when specified
- **REQ-OUT-007:** DEF component placement SHALL be offset by margins
- **REQ-OUT-008:** Edge cells SHALL be included as DEF components with proper naming

### 9.2 DEF Row Definitions
- **REQ-OUT-009:** DEF file SHALL include ROWS section with site-based row definitions
- **REQ-OUT-010:** Row definitions SHALL include top edge row if top edge cells enabled
- **REQ-OUT-011:** Row definitions SHALL include fabric rows (ROW_0, ROW_1, ..., ROW_N)
- **REQ-OUT-012:** Row definitions SHALL include bottom edge row if bottom edge cells enabled
- **REQ-OUT-013:** Row coordinates SHALL be in database units with proper margin offsets
- **REQ-OUT-014:** Row names SHALL follow standard DEF naming conventions

### 9.3 DEF Pin Definitions
- **REQ-OUT-015:** DEF pins SHALL include RECT definitions with configured dimensions
- **REQ-OUT-016:** Pin coordinates SHALL be converted to database units
- **REQ-OUT-017:** Pin placement SHALL respect margin boundaries
- **REQ-OUT-018:** Manual pin positions SHALL be used exactly as specified
- **REQ-OUT-019:** Auto-spaced pins SHALL be evenly distributed in margin area

### 9.4 LEF File Output
- **REQ-OUT-020:** LEF file SHALL define fabric as single macro block
- **REQ-OUT-021:** LEF file SHALL include I/O pin definitions and locations
- **REQ-OUT-022:** LEF file SHALL specify routing layers met3-met5
- **REQ-OUT-023:** LEF file SHALL include physical dimensions and site information
- **REQ-OUT-024:** LEF macro size SHALL include margins in die area
- **REQ-OUT-025:** LEF pin positions SHALL be placed in margin areas
- **REQ-OUT-026:** LEF pin definitions SHALL use configured pin size
- **REQ-OUT-027:** Pin rectangles SHALL be centered on specified positions

### 9.5 JSON Output
- **REQ-OUT-028:** JSON output SHALL provide complete fabric representation
- **REQ-OUT-029:** JSON output SHALL include cell positions and tile assignments
- **REQ-OUT-030:** JSON output SHALL provide fabric statistics (cell counts, area, resources)
- **REQ-OUT-031:** JSON output SHALL be human-readable and well-formatted
- **REQ-OUT-032:** JSON output SHALL include edge cell information
- **REQ-OUT-033:** JSON output SHALL include margin and core area information
- **REQ-OUT-034:** JSON statistics SHALL count edge cells separately
- **REQ-OUT-035:** JSON output SHALL include I/O pin position information

---

## 10. VISUALIZATION REQUIREMENTS

### 10.1 Fabric SVG Requirements
- **REQ-VIS-001:** Tool SHALL generate fabric SVG showing die area, core area, and tiles
- **REQ-VIS-002:** Fabric SVG SHALL show die area boundary in red
- **REQ-VIS-003:** Fabric SVG SHALL show core area boundary in blue
- **REQ-VIS-004:** Fabric SVG SHALL show tile instances as colored rectangles with names
- **REQ-VIS-005:** Fabric SVG SHALL show edge cells around fabric perimeter
- **REQ-VIS-006:** Fabric SVG SHALL show I/O pins as small symbols on die edges
- **REQ-VIS-007:** Fabric SVG SHALL use proportional scaling based on actual micron dimensions
- **REQ-VIS-008:** Fabric SVG SHALL NOT show individual cell details within tiles

### 10.2 Tile SVG Requirements
- **REQ-VIS-009:** Tool SHALL generate individual SVG files for each tile type used in fabric
- **REQ-VIS-010:** Tile SVG files SHALL be named tile_TILETYPE.svg
- **REQ-VIS-011:** Tile SVG SHALL show individual cells with proportional dimensions
- **REQ-VIS-012:** Tile SVG SHALL show grid lines for site boundaries
- **REQ-VIS-013:** Tile SVG SHALL show row separations clearly marked
- **REQ-VIS-014:** Tile SVG SHALL show cell names/labels when space permits
- **REQ-VIS-015:** Tile SVG SHALL show physical dimensions and scale information
- **REQ-VIS-016:** Tile SVG files SHALL be generated in same output directory

### 10.3 Color Scheme Requirements
- **REQ-VIS-017:** Logic cells (NAND, NOR, INV, etc.) SHALL use distinct colors
- **REQ-VIS-018:** Sequential cells (DFF, LATCH, etc.) SHALL use distinct colors
- **REQ-VIS-019:** Physical cells (TAP, CONB) SHALL use distinct colors
- **REQ-VIS-020:** All DECAP cells SHALL use same color regardless of size
- **REQ-VIS-021:** Edge cells SHALL use distinct color in fabric visualization
- **REQ-VIS-022:** Different tile types SHALL use distinct background colors
- **REQ-VIS-023:** I/O pins SHALL use distinct color (gold) for visibility

### 10.4 Legend Requirements
- **REQ-VIS-024:** Fabric SVG SHALL include comprehensive legend showing:
  - Die area boundary (red line)
  - Core area boundary (blue line)
  - Tile types with colors
  - Edge cells with color
  - I/O pins with symbol

- **REQ-VIS-025:** Tile SVG SHALL include title with tile type, dimensions, cell count, and area
- **REQ-VIS-033:** SVG generation SHALL log figure dimensions and vector format confirmation

### 10.5 Scalable Vector Graphics Requirements
- **REQ-VIS-026:** All visualizations SHALL maintain accurate aspect ratios
- **REQ-VIS-027:** Scaling SHALL be based on actual physical dimensions in microns
- **REQ-VIS-028:** SVG format SHALL provide infinite scalability without quality loss
- **REQ-VIS-029:** Cell sizes in tile SVG SHALL reflect true width/height ratios
- **REQ-VIS-030:** Font sizes and visual elements SHALL scale adaptively based on fabric complexity
- **REQ-VIS-031:** Vector graphics SHALL ensure crisp text and lines at all zoom levels
- **REQ-VIS-032:** SVG files SHALL be optimized for web browsers and documentation systems
- **REQ-VIS-034:** Grid lines and subtle visual elements SHALL enhance readability without cluttering

---

## 11. OUTPUT NAMING REQUIREMENTS

### 11.1 Automatic Name/Directory Matching
- **REQ-NAME-006:** If only --output-dir path/name provided, extract "name" as base name
- **REQ-NAME-007:** If only --output-name name provided, create directory "name/"
- **REQ-NAME-008:** If both provided, use both as specified
- **REQ-NAME-009:** Base name SHALL default to fabric JSON name if neither provided

### 11.2 Output File Naming
- **REQ-NAME-010:** Main outputs SHALL use base name: basename.def, basename.lef, etc.
- **REQ-NAME-011:** Tile SVGs SHALL use format: tile_TILETYPE.svg
- **REQ-NAME-012:** All outputs SHALL be generated in specified output directory

---

## 12. PERFORMANCE REQUIREMENTS

### 12.1 Scalability
- **REQ-PERF-001:** Tool SHALL support fabric arrays up to 100×100 tiles
- **REQ-PERF-002:** Tool SHALL complete processing for 10×10 fabric within 10 seconds
- **REQ-PERF-003:** Memory usage SHALL scale linearly with fabric size
- **REQ-PERF-004:** Tool SHALL provide progress indication for large fabrics

### 12.2 Resource Requirements
- **REQ-PERF-005:** Tool SHALL run on systems with minimum 4GB RAM
- **REQ-PERF-006:** Tool SHALL support standard Python 3.8+ installations
- **REQ-PERF-007:** Tool SHALL have minimal external dependencies

---

## 13. INTERFACE REQUIREMENTS

### 13.1 Command Line Interface
```bash
python gen_fabric.py technology.json tiles.json fabric.json [options]

Required Arguments:
  technology.json         Technology definition file
  tiles.json             Tile definitions file  
  fabric.json            Fabric configuration file

Options:
  --output-dir DIR        Output directory (default: current directory)
  --output-name NAME      Output file base name (default: fabric name)
  --pin-size WIDTH HEIGHT Pin rectangle size in DB units (default: 1.0 1.0)
  --pin-size-um WIDTH HEIGHT Pin rectangle size in microns
  --def-only             Generate only DEF file
  --verbose              Enable verbose output
  --quiet                Suppress non-error output
  --help                 Show usage information
  --version              Show version information
```

**Requirements:**
- **REQ-CLI-001:** Tool SHALL accept command line arguments for input/output files
- **REQ-CLI-002:** Tool SHALL provide usage help and version information
- **REQ-CLI-003:** Tool SHALL support verbose and quiet operation modes
- **REQ-CLI-004:** Tool SHALL return appropriate exit codes (0=success, 1=error)
- **REQ-CLI-005:** Tool SHALL accept pin size configuration via command line
- **REQ-CLI-006:** Pin size SHALL be specified in database units or microns
- **REQ-CLI-007:** Command line pin size SHALL override fabric JSON specification

### 13.2 Integration Requirements
- **REQ-INT-001:** Tool SHALL integrate with broader Sky130 design flow
- **REQ-INT-002:** Generated DEF files SHALL be compatible with structured ASIC placer
- **REQ-INT-003:** Tool SHALL support batch processing of multiple fabric configurations
- **REQ-INT-004:** Tool SHALL provide machine-readable status and error reporting

---

## 14. STATISTICS REQUIREMENTS

### 14.1 Fabric Statistics
- **REQ-STAT-001:** Statistics SHALL include tile array dimensions (N×M tiles)
- **REQ-STAT-002:** Statistics SHALL include fabric dimensions (rows×sites)
- **REQ-STAT-003:** Statistics SHALL include core area dimensions including edge cells
- **REQ-STAT-004:** Statistics SHALL include die area and core area dimensions
- **REQ-STAT-005:** Statistics SHALL include cell counts by type and category

### 14.2 Edge Cell Statistics
- **REQ-STAT-006:** Statistics SHALL include edge cell counts by type and direction
- **REQ-STAT-007:** Statistics SHALL show edge cell dimensions and positions
- **REQ-STAT-008:** Statistics SHALL report edge cell utilization separately from fabric cells

### 14.3 Dimensional Statistics
- **REQ-STAT-009:** Statistics SHALL show fabric dimensions in both sites and microns
- **REQ-STAT-010:** Statistics SHALL show core area dimensions including edge cell contributions
- **REQ-STAT-011:** Statistics SHALL include margin information when specified
- **REQ-STAT-012:** Statistics SHALL provide area calculations in μm²

### 14.4 I/O Pin Statistics
- **REQ-STAT-013:** Statistics SHALL include I/O pin counts by edge and type
- **REQ-STAT-014:** Statistics SHALL include pin positioning mode per edge
- **REQ-STAT-015:** Statistics SHALL include configured pin dimensions

---

## 15. QUALITY REQUIREMENTS

### 15.1 Reliability
- **REQ-QUA-001:** Tool SHALL validate all inputs before processing
- **REQ-QUA-002:** Tool SHALL handle edge cases gracefully
- **REQ-QUA-003:** Tool SHALL provide deterministic outputs for identical inputs
- **REQ-QUA-004:** Tool SHALL include comprehensive error checking

### 15.2 Maintainability
- **REQ-QUA-005:** Code SHALL follow Python PEP 8 style guidelines
- **REQ-QUA-006:** Code SHALL include comprehensive docstrings and comments
- **REQ-QUA-007:** Code SHALL be modular with clear separation of concerns
- **REQ-QUA-008:** Code SHALL include unit tests for all major functions

### 15.3 Documentation
- **REQ-DOC-001:** Tool SHALL include comprehensive user documentation
- **REQ-DOC-002:** Tool SHALL include API documentation for all public functions
- **REQ-DOC-003:** Tool SHALL include example configurations and tutorials
- **REQ-DOC-004:** Tool SHALL include troubleshooting and FAQ sections

---

## 16. EXAMPLE USE CASES

### 16.1 Basic 5×5 Fabric Example
**Configuration:**
- 5×5 tile array using Logic_4x60 tiles
- DECAP12 left/right edge cells
- DECAP4 top/bottom edge cells
- 50μm horizontal margins, 30μm vertical margins

**Expected Results:**
- Fabric dimensions: 20 rows × 300 sites
- Edge cells: 20 left + 20 right + spanning top/bottom
- Core area: 324 sites × 22 rows (148.94 × 59.84 μm)
- Die area: Core + 2×margins (248.94 × 119.84 μm)

### 16.2 Regional Override Example
**Configuration:**
- 3×3 tile array with Logic_4x60 default
- Memory_4x60 region at (1,1) with 2×2 area
- Edge cells on all sides

**Expected Results:**
- Center 4 tiles use Memory_4x60
- Outer 5 tiles use Logic_4x60
- Edge cells around complete perimeter

---

## 17. IMPLEMENTATION PHASES

### Phase 1: Core Functionality
- JSON parsing and validation
- Basic fabric generation with default tiles
- Region processing and overlap detection
- Cell naming convention implementation
- DEF file output generation with rows

### Phase 2: Edge Cell Implementation
- Edge cell placement logic
- Core area dimension calculations
- Proper coordinate system handling
- Edge cell validation and error checking
- Updated statistics reporting

### Phase 3: Enhanced Visualization
- Die area and core area visualization
- Proportional scaling implementation
- Individual tile SVG generation
- Color coding and legend implementation
- I/O pin visualization

### Phase 4: I/O Ring Enhancements
- Manual pin positioning support
- Pin size configuration
- Pin overlap validation
- Enhanced LEF/DEF pin output
- Backward compatibility testing

### Phase 5: Integration and Quality
- Output naming enhancements
- Comprehensive testing and validation
- Performance optimization
- Documentation completion
- Example configurations and tutorials

---

**END OF COMPLETE FORMAL REQUIREMENTS SPECIFICATION**
